"""命令行入口。

命令参数解析在这里重写（原项目是聊天命令，这里是 argparse + REST）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import suppress

from .config import load_settings
from .core.archive import ArchiveQueue, ArchiveStore
from .core.auth import MucAuthService
from .core.engine import NoticeEngine
from .core.fetcher import MucRssService
from .core.sources import SOURCES
from .core.storage import NoticeStore
from .transport.publishers import SubscriberStore, WebhookPublisher

logger = logging.getLogger("muc_notice_engine")


def _setup_logging(verbose: bool) -> None:
    # Windows 控制台默认 GBK，通知标题可能含零宽空格等字符导致 print 崩溃。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _build(settings):
    store = NoticeStore(settings.db_path)
    auth = MucAuthService(settings)
    fetcher = MucRssService(settings, auth)
    subscribers = SubscriberStore(settings.db_path)
    return store, auth, fetcher, subscribers


def _parse_source_keys(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {s.strip() for s in raw.split(",") if s.strip()}


# ---------------- run ----------------

def cmd_run(args: argparse.Namespace) -> int:
    import uvicorn

    from .transport.api import create_app

    overrides = {}
    if args.host:
        overrides["api_host"] = args.host
    if args.port:
        overrides["api_port"] = args.port
    if args.poll_interval is not None:
        overrides["poll_interval_minutes"] = args.poll_interval
    settings = load_settings(args.config, overrides)

    store, auth, fetcher, subscribers = _build(settings)
    publisher = WebhookPublisher(subscribers, settings)
    archive_queue: ArchiveQueue | None = None
    archive_store: ArchiveStore | None = None
    if settings.archive_enable:
        archive_store = ArchiveStore(settings, store, auth)
        archive_queue = ArchiveQueue(settings, store, fetcher, archive_store)
    engine = NoticeEngine(
        settings, fetcher, store, [publisher], archiver=archive_queue
    )
    app = create_app(
        engine=engine,
        store=store,
        settings=settings,
        fetcher=fetcher,
        subscribers=subscribers,
        archive_store=archive_store,
    )

    async def _serve() -> None:
        config = uvicorn.Config(
            app,
            host=settings.api_host,
            port=settings.api_port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        if archive_queue is not None:
            await archive_queue.start()
        poll_task = asyncio.create_task(engine.run_forever())
        try:
            await server.serve()
        finally:
            engine.stop()
            poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await poll_task
            if archive_queue is not None:
                await archive_queue.stop()
            await auth.close()
            store.close()
            subscribers.close()

    logger.info(
        "启动服务：http://%s:%s  (轮询间隔 %s 分钟)",
        settings.api_host,
        settings.api_port,
        settings.poll_interval_minutes,
    )
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        logger.info("收到中断，退出。")
    return 0


# ---------------- poll / fetch ----------------

def cmd_poll(args: argparse.Namespace) -> int:
    settings = load_settings(args.config, {"poll_on_start": False})
    source_keys = _parse_source_keys(args.source)

    async def _run() -> None:
        store, auth, fetcher, subscribers = _build(settings)
        engine = NoticeEngine(settings, fetcher, store)
        try:
            fresh = await engine.poll_once(source_keys)
            for n in fresh:
                print(f"[{n.source}] {n.date} | {n.title}\n  {n.link}")
            print(f"共 {len(fresh)} 条新通知")
        finally:
            await auth.close()
            store.close()
            subscribers.close()

    asyncio.run(_run())
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    for s in SOURCES:
        auth_mark = " [需登录]" if s.get("requires_auth") else ""
        print(f"{s['key']:<10} {s['name']}{auth_mark}")
    print(f"共 {len(SOURCES)} 个来源")
    return 0


def cmd_rss(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    source_keys = _parse_source_keys(args.source)

    async def _run() -> None:
        store, auth, fetcher, subscribers = _build(settings)
        try:
            notices = await fetcher.fetch_notices(source_keys)
            await fetcher.write_rss(notices)
            print(f"已写入 {fetcher.rss_file_path}（{len(notices)} 条）")
        finally:
            await auth.close()
            store.close()
            subscribers.close()

    asyncio.run(_run())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muc-notice-engine",
        description="中央民族大学多站点通知聚合 / 存储 / 去重引擎",
    )
    parser.add_argument("--config", default=None, help="config.toml 路径")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="启动常驻服务（REST API + 定时轮询 + webhook）")
    p_run.add_argument("--host", default=None)
    p_run.add_argument("--port", type=int, default=None)
    p_run.add_argument("--poll-interval", type=int, default=None, help="轮询间隔（分钟）")
    p_run.set_defaults(func=cmd_run)

    p_poll = sub.add_parser("poll", help="立即抓取一轮（打印新通知）")
    p_poll.add_argument("--source", default=None, help="逗号分隔的 source_key")
    p_poll.set_defaults(func=cmd_poll)

    p_sources = sub.add_parser("sources", help="列出所有来源")
    p_sources.set_defaults(func=cmd_sources)

    p_rss = sub.add_parser("rss", help="抓取并生成 RSS 文件")
    p_rss.add_argument("--source", default=None)
    p_rss.set_defaults(func=cmd_rss)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))
    return args.func(args)
