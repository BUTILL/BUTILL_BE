from app.schemas.ingredient_prices import PriceItem

# 코드는 aT 코드표와 2026-10 서울 소매 실데이터로 확인했다. 품종을 비운 품목은 계절마다 품종이 바뀐다.
PRICE_ITEMS = [
    PriceItem(key="rice", name="쌀", groups=["common"], category_code="100", item_code="111", kind_code="01", rank_code="04"),
    PriceItem(key="onion", name="양파", groups=["common"], category_code="200", item_code="245", kind_code="00", rank_code="04"),
    PriceItem(key="green_onion", name="대파", groups=["common"], category_code="200", item_code="246", kind_code="00", rank_code="04"),
    PriceItem(key="garlic", name="깐마늘(국산)", groups=["common"], category_code="200", item_code="258", kind_code="01", rank_code="04"),
    PriceItem(key="napa_cabbage", name="배추", groups=["common"], category_code="200", item_code="211", rank_code="04"),
    PriceItem(key="egg", name="계란(특란 30구)", groups=["common"], category_code="500", item_code="9903", kind_code="23", rank_code="1"),
    PriceItem(key="chicken", name="닭(육계)", groups=["dakgalbi"], category_code="500", item_code="9901", kind_code="99", rank_code="1"),
    PriceItem(key="sweet_potato", name="고구마", groups=["dakgalbi"], category_code="100", item_code="151", kind_code="00", rank_code="04"),
    PriceItem(key="cabbage", name="양배추", groups=["dakgalbi"], category_code="200", item_code="212", kind_code="00", rank_code="04"),
    PriceItem(key="perilla_leaf", name="깻잎", groups=["dakgalbi"], category_code="200", item_code="253", kind_code="00", rank_code="04"),
    PriceItem(key="chives", name="부추", groups=["dakgalbi"], category_code="200", item_code="254", kind_code="00", rank_code="04"),
    PriceItem(key="water_parsley", name="미나리", groups=["dakgalbi"], category_code="200", item_code="252", kind_code="00", rank_code="04"),
    PriceItem(key="red_pepper_powder", name="고춧가루(국산)", groups=["dakgalbi"], category_code="200", item_code="248", kind_code="00", rank_code="04"),
    PriceItem(key="radish", name="무", groups=["dakgalbi"], category_code="200", item_code="231", rank_code="04"),
    PriceItem(key="tomato", name="토마토", groups=["pasta"], category_code="200", item_code="225", kind_code="00", rank_code="04"),
    PriceItem(key="cherry_tomato", name="방울토마토", groups=["pasta"], category_code="200", item_code="422", rank_code="04"),
    PriceItem(key="lemon", name="레몬", groups=["pasta"], category_code="400", item_code="424", kind_code="00", rank_code="04"),
    PriceItem(key="shrimp", name="새우(흰다리)", groups=["pasta"], category_code="600", item_code="654", kind_code="01"),
    PriceItem(key="squid", name="물오징어(원양 냉동)", groups=["pasta"], category_code="600", item_code="619", kind_code="05", rank_code="22"),
    PriceItem(key="clam", name="바지락", groups=["pasta"], category_code="600", item_code="661", kind_code="00"),
]
