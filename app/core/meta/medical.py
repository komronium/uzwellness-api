from app.core.meta.shared import Label, Option, from_labels


_NATURAL_RESOURCE: dict[str, Label] = {
    "thermal_mineral_water": {
        "uz": "Termal mineral suv",
        "ru": "Термальная минеральная вода",
        "en": "Thermal mineral water",
    },
    "drinking_mineral_water": {
        "uz": "Shifobaxsh ichimlik mineral suv",
        "ru": "Лечебная питьевая минеральная вода",
        "en": "Healing drinking mineral water",
    },
    "mud": {
        "uz": "Shifobaxsh balchiq/loy",
        "ru": "Лечебная грязь",
        "en": "Healing mud",
    },
    "co2_gas": {
        "uz": "Tabiiy karbonat angidrid gazi",
        "ru": "Природный углекислый газ",
        "en": "Natural carbon dioxide gas",
    },
    "climate": {
        "uz": "Shifobaxsh iqlim",
        "ru": "Лечебный климат",
        "en": "Healing climate",
    },
    "mountain_air": {"uz": "Tog' havosi", "ru": "Горный воздух", "en": "Mountain air"},
    "spring_water": {
        "uz": "Buloq suvi",
        "ru": "Родниковая вода",
        "en": "Spring water",
    },
    "forest_zone": {
        "uz": "O'rmon zonasi",
        "ru": "Лесная зона",
        "en": "Forest zone",
    },
    "clean_air": {"uz": "Toza havo", "ru": "Чистый воздух", "en": "Clean air"},
    "urban_wellness": {
        "uz": "Shahar wellness muhiti",
        "ru": "Городская wellness-среда",
        "en": "Urban wellness setting",
    },
    "salt_cave": {"uz": "Tuz g'ori", "ru": "Соляная пещера", "en": "Salt cave"},
}

_MEDICAL_PROCEDURE_CATEGORY: dict[str, Label] = {
    "hydrotherapy": {"uz": "Gidroterapiya", "ru": "Гидротерапия", "en": "Hydrotherapy"},
    "physiotherapy": {
        "uz": "Fizioterapiya",
        "ru": "Физиотерапия",
        "en": "Physiotherapy",
    },
    "thermotherapy": {
        "uz": "Termoterapiya (Issiqlik)",
        "ru": "Термотерапия",
        "en": "Thermotherapy",
    },
    "massages": {"uz": "Massajlar", "ru": "Массажи", "en": "Massages"},
    "kinesitherapy": {
        "uz": "Kineziterapiya (Davolash gimnastikasi)",
        "ru": "Кинезитерапия",
        "en": "Kinesitherapy",
    },
    "other": {
        "uz": "Boshqa muolajalar",
        "ru": "Другие процедуры",
        "en": "Other treatments",
    },
}

_MEDICAL_PROCEDURE: dict[str, Label] = {
    "circular_shower": {
        "uz": "Sirkulyar dush",
        "ru": "Циркулярный душ",
        "en": "Circular shower",
    },
    "charcot_shower": {"uz": "Sharko dushi", "ru": "Душ Шарко", "en": "Charcot shower"},
    "sharko_shower": {"uz": "Sharko dushi", "ru": "Душ Шарко", "en": "Charcot shower"},
    "cascade_shower": {
        "uz": "Kaskad dush",
        "ru": "Каскадный душ",
        "en": "Cascade shower",
    },
    "hydrocolonotherapy": {
        "uz": "Gidrokolonoterapiya",
        "ru": "Гидроколонотерапия",
        "en": "Hydrocolonotherapy",
    },
    "colon_hydrotherapy": {
        "uz": "Gidrokolonoterapiya",
        "ru": "Гидроколонотерапия",
        "en": "Colon hydrotherapy",
    },
    "hydromassage_bath": {
        "uz": "Tibbiy gidromassajli vanna",
        "ru": "Медицинская гидромассажная ванна",
        "en": "Medical hydromassage bath",
    },
    "medical_hydromassage_bath": {
        "uz": "Tibbiy gidromassajli vanna",
        "ru": "Медицинская гидромассажная ванна",
        "en": "Medical hydromassage bath",
    },
    "vichy_shower": {"uz": "Vishi dushi", "ru": "Душ Виши", "en": "Vichy shower"},
    "ascending_shower": {
        "uz": "Ko'tariluvchi dush",
        "ru": "Восходящий душ",
        "en": "Ascending shower",
    },
    "pearl_baths": {
        "uz": "Marvaridli vannalar",
        "ru": "Жемчужные ванны",
        "en": "Pearl baths",
    },
    "hand_baths": {"uz": "Qo'l vannalari", "ru": "Ручные ванны", "en": "Hand baths"},
    "foot_baths": {"uz": "Oyoq vannalari", "ru": "Ножные ванны", "en": "Foot baths"},
    "carbon_dioxide_bath": {
        "uz": "Karbonat angidridli vanna",
        "ru": "Углекислая ванна",
        "en": "Carbon dioxide bath",
    },
    "mineral_bath": {
        "uz": "Mineral vanna",
        "ru": "Минеральная ванна",
        "en": "Mineral bath",
    },
    "ecg": {"uz": "EKG", "ru": "ЭКГ", "en": "ECG"},
    "uhf_ultratherm": {
        "uz": "UVCh-Ultraterm",
        "ru": "УВЧ-Ультратерм",
        "en": "UHF-Ultratherm",
    },
    "radiotherm": {"uz": "Radioterm", "ru": "Радиотерм", "en": "Radiotherm"},
    "interference_therapy": {
        "uz": "Interferensiya terapiyasi",
        "ru": "Интерференцтерапия",
        "en": "Interference therapy",
    },
    "stereodinator": {
        "uz": "Stereodinator",
        "ru": "Стереодинатор",
        "en": "Stereodinator",
    },
    "neuroton": {"uz": "Neyroton", "ru": "Нейротон", "en": "Neuroton"},
    "massage_couch": {
        "uz": "Massaj kushedkasi",
        "ru": "Массажная кушетка",
        "en": "Massage couch",
    },
    "laser_therapy": {
        "uz": "Lazero-terapiya",
        "ru": "Лазеротерапия",
        "en": "Laser therapy",
    },
    "darsonvalization": {
        "uz": "Darsonvalizatsiya",
        "ru": "Дарсонвализация",
        "en": "Darsonvalization",
    },
    "hi_top": {"uz": "Hi-Top terapiya", "ru": "Hi-Top", "en": "Hi-Top therapy"},
    "mechanotherapy": {
        "uz": "Mexano-massaj",
        "ru": "Механомассаж",
        "en": "Mechanotherapy",
    },
    "mechanomassage": {
        "uz": "Mexano-massaj",
        "ru": "Механомассаж",
        "en": "Mechanomassage",
    },
    "ufo_tubus": {"uz": "UFO (tubus)", "ru": "УФО (тубус)", "en": "UFO (tubus)"},
    "inhalation": {"uz": "Ingalyatsiya", "ru": "Ингаляция", "en": "Inhalation"},
    "magnetotherapy": {
        "uz": "Magnito-terapiya",
        "ru": "Магнитотерапия",
        "en": "Magnetotherapy",
    },
    "infra_red": {"uz": "Infraruj (Infraqizil)", "ru": "Инфраруж", "en": "Infrared"},
    "infrared": {"uz": "Infraruj", "ru": "Инфраруж", "en": "Infrared therapy"},
    "phonophoresis": {"uz": "Fonoforez", "ru": "Фонофорез", "en": "Phonophoresis"},
    "ozonotherapy": {"uz": "Ozonoterapiya", "ru": "Озонотерапия", "en": "Ozonotherapy"},
    "lymphatic_drainage": {
        "uz": "Limfodrenaj",
        "ru": "Лимфодренаж",
        "en": "Lymphatic drainage",
    },
    "paraffin_wraps": {
        "uz": "Parafinli o'ramlar",
        "ru": "Парафиновые аппликации",
        "en": "Paraffin wraps",
    },
    "mud_applications": {
        "uz": "Balchiqli applikatsiyalar",
        "ru": "Грязевые аппликации",
        "en": "Mud applications",
    },
    "sauna": {"uz": "Sauna", "ru": "Сауна", "en": "Sauna"},
    "classical_massage": {
        "uz": "Klassik massaj",
        "ru": "Классический массаж",
        "en": "Classical massage",
    },
    "massage": {"uz": "Massaj", "ru": "Массаж", "en": "Massage"},
    "local_massage": {
        "uz": "Lokal (mahalliy) massaj",
        "ru": "Лечебный массаж (локально)",
        "en": "Local therapeutic massage",
    },
    "pool_gymnastics": {
        "uz": "Hovuzdagi gimnastika",
        "ru": "Гимнастика в бассейне",
        "en": "Gymnastics in the pool",
    },
    "individual_kinesitherapy": {
        "uz": "Individual davolash gimnastikasi",
        "ru": "Индивидуальная гимнастика",
        "en": "Individual kinesitherapy",
    },
    "meals_4x": {
        "uz": "4 mahal ovqatlanish",
        "ru": "4-х разовое питание",
        "en": "4 meals per day",
    },
    "phyto_bar": {"uz": "Fito bar", "ru": "Фито бар", "en": "Phyto bar"},
    "pool_access": {
        "uz": "Yopiq va ochiq basseyn",
        "ru": "Крытый и Открытый бассейн",
        "en": "Indoor & Outdoor pool",
    },
    "playstation_room": {
        "uz": "Play Station o'yin xonasi",
        "ru": "Комната для игры Play Station",
        "en": "Play Station games room",
    },
    "bicycles": {
        "uz": "Velosipedlar",
        "ru": "Велосипеды на территории",
        "en": "Bicycles on site",
    },
    "hippotherapy": {
        "uz": "Ippoterapiya (otda sayr)",
        "ru": "Иппотерапия (лечебные прогулки)",
        "en": "Hippotherapy",
    },
    "doctor_consultation": {
        "uz": "Shifokor nazorati",
        "ru": "Осмотр и наблюдение врачей",
        "en": "Doctor checkups",
    },
    "lab_tests": {
        "uz": "Laboratoriya tahlillari",
        "ru": "Лабораторные анализы",
        "en": "Laboratory tests",
    },
}


def medical_meta() -> dict[str, list[Option]]:
    return {
        "natural_resources": from_labels(_NATURAL_RESOURCE),
        "medical_procedure_categories": from_labels(_MEDICAL_PROCEDURE_CATEGORY),
        "medical_procedures": from_labels(_MEDICAL_PROCEDURE),
    }
