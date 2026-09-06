"""
教育技术学权威期刊清单（含中英文）
ISSN 用于 OpenAlex / Crossref 过滤，确保只取自权威来源的文献。
"""

# 国际 SSCI / SCI 教育技术学顶刊
# 来源：教育技术学领域公认权威，按2024 JCR / Scopus 排名
INTERNATIONAL_JOURNALS = [
    {
        "name": "Educational Technology Research and Development",
        "abbr": "ETR&D",
        "issn": "1042-1629",
        "publisher": "Springer",
        "language": "en",
        "homepage": "https://link.springer.com/journal/11423",
    },
    {
        "name": "Computers & Education",
        "abbr": "C&E",
        "issn": "0360-1315",
        "publisher": "Elsevier",
        "language": "en",
        "homepage": "https://www.sciencedirect.com/journal/computers-and-education",
    },
    {
        "name": "Internet and Higher Education",
        "abbr": "IHE",
        "issn": "1096-7516",
        "publisher": "Elsevier",
        "language": "en",
        "homepage": "https://www.sciencedirect.com/journal/internet-and-higher-education",
    },
    {
        "name": "British Journal of Educational Technology",
        "abbr": "BJET",
        "issn": "0007-1013",
        "publisher": "Wiley",
        "language": "en",
        "homepage": "https://bera-journals.onlinelibrary.wiley.com/journal/14678535",
    },
    {
        "name": "Journal of Computer Assisted Learning",
        "abbr": "JCAL",
        "issn": "0266-4909",
        "publisher": "Wiley",
        "language": "en",
        "homepage": "https://onlinelibrary.wiley.com/journal/10990890",
    },
    {
        "name": "Educational Technology & Society",
        "abbr": "ET&S",
        "issn": "1176-3647",
        "publisher": "IEEE / Learning Technology Consortium",
        "language": "en",
        "homepage": "https://www.jstor.org/journal/eductechsoci",
    },
    {
        "name": "American Journal of Distance Education",
        "abbr": "AJDE",
        "issn": "0892-3647",
        "publisher": "Taylor & Francis",
        "language": "en",
        "homepage": "https://www.tandfonline.com/toc/hajd20/current",
    },
    {
        "name": "Distance Education",
        "abbr": "DE",
        "issn": "0158-7919",
        "publisher": "Taylor & Francis",
        "language": "en",
        "homepage": "https://www.tandfonline.com/toc/cjad20/current",
    },
    {
        "name": "Learning and Instruction",
        "abbr": "L&I",
        "issn": "0959-4752",
        "publisher": "Elsevier",
        "language": "en",
        "homepage": "https://www.sciencedirect.com/journal/learning-and-instruction",
    },
    {
        "name": "Journal of Educational Technology & Online Learning",
        "abbr": "JETOL",
        "issn": "2636-8404",
        "publisher": "JETOL",
        "language": "en",
        "homepage": "https://dergipark.org.tr/en/pub/jetol",
    },
]

# 国内 CSSCI / 北大核心 教育技术学权威期刊
DOMESTIC_JOURNALS = [
    {
        "name": "电化教育研究",
        "abbr": "电教研究",
        "issn": "1003-1553",
        "publisher": "西北师范大学",
        "language": "zh",
        "homepage": "http://www.nwnu.edu.cn",
    },
    {
        "name": "中国远程教育",
        "abbr": "中远教",
        "issn": "1009-4583",
        "publisher": "国家开放大学",
        "language": "zh",
        "homepage": "https://www.zhongyuanzhiyejiaoyu.com",
    },
    {
        "name": "开放教育研究",
        "abbr": "开放教研",
        "issn": "1007-2179",
        "publisher": "上海远程教育集团",
        "language": "zh",
        "homepage": "https://openedu.sou.edu.cn",
    },
    {
        "name": "现代教育技术",
        "abbr": "现教技",
        "issn": "1009-8097",
        "publisher": "清华大学",
        "language": "zh",
        "homepage": "https://xjjyjs.tsinghua.edu.cn",
    },
    {
        "name": "现代远程教育研究",
        "abbr": "现远教研",
        "issn": "1009-5198",
        "publisher": "四川开放大学",
        "language": "zh",
        "homepage": "https://www.sccvu.edu.cn",
    },
    {
        "name": "远程教育杂志",
        "abbr": "远教杂志",
        "issn": "1672-0008",
        "publisher": "浙江开放大学",
        "language": "zh",
        "homepage": "https://dejx.czie.net.cn",
    },
    {
        "name": "中国电化教育",
        "abbr": "中电教",
        "issn": "1006-9860",
        "publisher": "中央电化教育馆",
        "language": "zh",
        "homepage": "https://www.ncet.edu.cn",
    },
    {
        "name": "教育技术研究",
        "abbr": "教研",
        "issn": "1671-489X",  # 部分版本 ISSN 收录
        "publisher": "天津电化教育馆",
        "language": "zh",
        "homepage": "http://www.tje.cn",
    },
]

ALL_JOURNALS = INTERNATIONAL_JOURNALS + DOMESTIC_JOURNALS


def get_issn_list():
    """返回所有期刊的 ISSN 列表（用于 OpenAlex 过滤）。"""
    return [j["issn"] for j in ALL_JOURNALS]


def journal_lookup():
    """ISSN → 期刊元数据 映射表，方便格式化时使用。"""
    return {j["issn"]: j for j in ALL_JOURNALS}