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
from .core.aop import AOP_SITES, AopSearchClient, resolve_site
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


def cmd_search(args: argparse.Namespace) -> int:
    if not args.site:
        for site in AOP_SITES:
            print(f"{site.key:<10} {site.name}  {site.host}  owner={site.owner}")
        print(f"共 {len(AOP_SITES)} 个可检索站点")
        return 0
    if not args.keyword:
        print("错误：给了 --site 就必须给 --keyword")
        return 2

    target = resolve_site(args.site)
    if target is None:
        print(f"错误：未知站点 --site={args.site}（用 `search` 不带参数列站点）")
        return 2

    async def _run() -> int:
        client = AopSearchClient()
        try:
            result = await client.search(
                target,
                args.keyword,
                match=args.match,
                exclude=args.exclude,
                scope=args.scope,
                order=args.order,
                since=args.since,
                until=args.until,
                limit=args.limit,
            )
        except ValueError as exc:
            print(f"参数错误：{exc}")
            return 2
        for hit in result.hits:
            print(
                f"[{hit.owner_name or hit.owner}] {hit.published_at:%Y-%m-%d %H:%M} | {hit.title}"
            )
            print(f"  {hit.link}")
        if result.error:
            print(f"远端错误：{result.error}")
        suffix = "，结果被截断" if result.truncated else ""
        print(
            f"共 {len(result.hits)} 条（远端 {result.remote_total} 条，"
            f"扫描 {result.scanned} 条{suffix}）"
        )
        return 0 if not result.error else 1

    return asyncio.run(_run())


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

    p_search = sub.add_parser("search", help="远程检索（AOP 智能搜索，不写库）")
    p_search.add_argument("--site", default=None, help="站点 key；不带则列出可检索站点")
    p_search.add_argument("--keyword", default=None, help="关键词，空格分隔")
    p_search.add_argument(
        "--match", choices=["all", "any"], default="any", help="all=全部关键词，any=任意一个"
    )
    p_search.add_argument("--exclude", default=None, help="空格分隔；命中标题/摘要任一词则排除")
    p_search.add_argument(
        "--scope", choices=["all", "title", "content"], default="all", help="检索范围"
    )
    p_search.add_argument(
        "--order", choices=["date", "score"], default="date", help="date=按时间，score=相关度"
    )
    p_search.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD")
    p_search.add_argument("--until", default=None, help="截止日期 YYYY-MM-DD")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=cmd_search)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))
    return args.func(args)
