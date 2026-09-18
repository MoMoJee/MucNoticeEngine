"""MUC 通知来源清单（21 个公开源 + 11 个门户类型）。

移植自 astrbot_plugin_MUC_Notices/sources.py。
新增/修改来源时，只需改这里；抓取逻辑在 fetcher.py 中保持通用。
链接拼接统一以当前页面 URL 为基准（urljoin），不再配置 base_url。
"""

from __future__ import annotations

import re

from .models import SourceConfig
from .parsers import (
    parse_selector_generic,
    parse_text_content,
    parse_title_attr,
)


def _portal_source(key: str, name: str, type_id: int, category: str) -> SourceConfig:
    return {
        "key": key,
        "name": name,
        "url": "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage",
        "selector": f"api:type={type_id}",
        "parser": parse_selector_generic,
        "category": category,
        "requires_auth": True,
        "api_params": {"currentPage": 1, "pageSize": 20, "type": type_id},
    }


SOURCES: list[SourceConfig] = [
    # ========== 主站通知公告 ==========
    {
        "key": "muc_tzgg",
        "name": "中央民族大学 - 通知公告",
        "url": "https://www.muc.edu.cn/tzgg.htm",
        "selector": ".list_box2 li a[title]",
        "parser": parse_title_attr,
        "category": "muc",
    },
    # ========== 研究生院 - 招生工作 ==========
    {
        "key": "grs_zs",
        "name": "研究生院 - 招生工作",
        "url": "https://grs.muc.edu.cn/",
        "selector": 'a[href*="info/1178/"]',
        "parser": parse_selector_generic,
        "category": "graduate",
    },
    # ========== 研究生院 - 培养工作 ==========
    {
        "key": "grs_py",
        "name": "研究生院 - 培养工作",
        "url": "https://grs.muc.edu.cn/pygz.htm",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
    },
    # ========== 研究生院 - 学位工作 ==========
    {
        "key": "grs_xw",
        "name": "研究生院 - 学位工作",
        "url": "https://grs.muc.edu.cn/xwgz.htm",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
    },
    # ========== 研究生院 - 学籍学生工作 ==========
    {
        "key": "grs_xj",
        "name": "研究生院 - 学籍学生工作",
        "url": "https://grs.muc.edu.cn/xj_xs_gz.htm",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
    },
    # ========== 研究生招生网 ==========
    {
        "key": "grs_yjszs",
        "name": "研究生院 - 研究生招生网",
        "url": "https://grs.muc.edu.cn/yjsyzsw/",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
    },
    # ========== 人事处 - 通知公告 ==========
    {
        "key": "rsc_tzgg",
        "name": "人事处 - 通知公告",
        "url": "https://rsc.muc.edu.cn/",
        "selector": 'a[href*="info/"][title]',
        "parser": parse_title_attr,
        "category": "rsc",
    },
    # ========== 财务处 - 通知公告 ==========
    {
        "key": "cwc_tzgg",
        "name": "财务处 - 通知公告",
        "url": "https://cwc.muc.edu.cn/",
        "selector": 'a[href*="info/"]',
        "parser": parse_selector_generic,
        "category": "cwc",
    },
    # ========== 新闻网 - 综合新闻 ==========
    {
        "key": "news_zh",
        "name": "新闻网 - 综合新闻",
        "url": "https://news.muc.edu.cn/",
        "selector": "a.eclip, a.a, a.ablink",
        "parser": parse_title_attr,
        "category": "news",
    },
    # ========== 新闻网 - 教学科研 ==========
    {
        "key": "news_xs",
        "name": "新闻网 - 教学科研",
        "url": "https://news.muc.edu.cn/jxky.htm",
        "selector": "h4 a",
        "parser": parse_title_attr,
        "category": "news",
    },
    # ========== 理学院 ==========
    {
        "key": "lxy_xydt",
        "name": "理学院 - 学院动态",
        "url": "https://lxy.muc.edu.cn/xydt1.htm",
        "selector": 'div.new_list3 dd a[href*="info/"]',
        "parser": parse_selector_generic,
        "category": "lxy",
    },
    {
        "key": "lxy_rcpy",
        "name": "理学院 - 人才培养",
        "url": "https://lxy.muc.edu.cn/rcpy.htm",
        "selector": 'div.new_list3 dd a[href*="info/"]',
        "parser": parse_selector_generic,
        "category": "lxy",
    },
    {
        "key": "lxy_kxyj",
        "name": "理学院 - 科学研究",
        "url": "https://lxy.muc.edu.cn/kxyj.htm",
        "selector": 'div.new_list3 dd a[href*="info/"]',
        "parser": parse_selector_generic,
        "category": "lxy",
    },
    # ========== 信息工程学院 ==========
    {
        "key": "xg_tzgg",
        "name": "信息工程学院 - 通知公告",
        "url": "https://xingong.muc.edu.cn/index/tzgg.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_kyjx",
        "name": "信息工程学院 - 科研教学",
        "url": "https://xingong.muc.edu.cn/index/kyjx.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_jwdt",
        "name": "信息工程学院 - 教务动态",
        "url": "https://xingong.muc.edu.cn/index/jwdt.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_dthd",
        "name": "信息工程学院 - 党团活动",
        "url": "https://xingong.muc.edu.cn/index/dthd.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_xyxw",
        "name": "信息工程学院 - 学院新闻",
        "url": "https://xingong.muc.edu.cn/index/xyxw.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_yjszs",
        "name": "信息工程学院 - 研究生招生",
        "url": "https://xingong.muc.edu.cn/zsjy/yjszs.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_bksjx",
        "name": "信息工程学院 - 本科生教学",
        "url": "https://xingong.muc.edu.cn/jyjx/bksjx.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    {
        "key": "xg_zyrz",
        "name": "信息工程学院 - 专业认证",
        "url": "https://xingong.muc.edu.cn/jyjx/zyrz.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": parse_selector_generic,
        "category": "xingong",
    },
    # ========== 信息门户 - 需登录（API，全量有效 type）==========
    _portal_source("my_xhw", "信息门户 - 新华网", 1, "news"),
    _portal_source("my_mzyw", "信息门户 - 民委要闻", 3, "news"),
    _portal_source("my_sztt", "信息门户 - 时政头条", 4, "news"),
    _portal_source("my_bgtz", "信息门户 - 办公通知", 5, "portal"),
    _portal_source("my_jxtz", "信息门户 - 教学通知", 6, "portal"),
    _portal_source("my_kytz", "信息门户 - 科研通知", 8, "portal"),
    _portal_source("my_xyxw", "信息门户 - 校园新闻", 9, "news"),
    _portal_source("my_jyxx", "信息门户 - 就业信息", 10, "career"),
    _portal_source("my_gsgg", "信息门户 - 公示公告", 11, "notice"),
    _portal_source("my_xgtz", "信息门户 - 学工通知", 32, "portal"),
    _portal_source("my_hdbd", "信息门户 - 活动报道", 36, "news"),
]

PORTAL_TYPES: dict[int, str] = {
    source["api_params"]["type"]: source["key"]
    for source in SOURCES
    if source.get("requires_auth", False) and "api_params" in source
}

SOURCES_BY_KEY: dict[str, SourceConfig] = {
    source["key"]: source for source in SOURCES if "key" in source
}


def resolve_source(query: str) -> SourceConfig | None:
    """按 key / 名称模糊匹配单个来源，匹配不唯一时返回 None。"""
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return None

    exact = SOURCES_BY_KEY.get(query.strip())
    if exact is not None:
        return exact

    matches = [
        source
        for source in SOURCES
        if normalized_query
        in {
            _normalize_query(source.get("key", "")),
            _normalize_query(source.get("name", "")),
        }
        or normalized_query in _normalize_query(source.get("key", ""))
        or normalized_query in _normalize_query(source.get("name", ""))
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def format_source_lines(subscribed_keys: set[str] | None = None) -> list[str]:
    subscribed_keys = subscribed_keys or set()
    lines: list[str] = []
    for source in SOURCES:
        status = " [已订阅]" if source["key"] in subscribed_keys else ""
        lines.append(f"- {source['key']}: {source['name']}{status}")
    return lines


def _normalize_query(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", text).casefold()
