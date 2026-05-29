from app.core.meta.shared import Label, Option, from_labels


_STAY_DURATION: dict[str, Label] = {
    "1_4": {"uz": "1-4 sutka", "ru": "1-4 суток", "en": "1-4 nights"},
    "5": {"uz": "5 sutka", "ru": "5 суток", "en": "5 nights"},
    "7": {"uz": "7 sutka", "ru": "7 суток", "en": "7 nights"},
    "10": {"uz": "10 sutka", "ru": "10 суток", "en": "10 nights"},
}

_STAY_PROGRAM_CATEGORY: dict[str, Label] = {
    "food": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Food"},
    "wellness": {"uz": "Wellness", "ru": "Wellness", "en": "Wellness"},
    "leisure": {"uz": "Dam olish", "ru": "Досуг", "en": "Leisure"},
    "service": {"uz": "Xizmatlar", "ru": "Услуги", "en": "Services"},
    "children": {"uz": "Bolalar", "ru": "Дети", "en": "Children"},
    "sport": {"uz": "Sport", "ru": "Спорт", "en": "Sport"},
    "medical": {"uz": "Tibbiy", "ru": "Медицина", "en": "Medical"},
}

_STAY_PROGRAM_INCLUSION: dict[str, Label] = {
    "meals_4x": {
        "uz": "4 mahal ovqatlanish",
        "ru": "4-х разовое питание",
        "en": "4 meals per day",
    },
    "phyto_bar": {"uz": "Fito bar", "ru": "Фито бар", "en": "Phyto bar"},
    "indoor_outdoor_pool": {
        "uz": "Yopiq va ochiq basseyn",
        "ru": "Крытый и открытый бассейн",
        "en": "Indoor and outdoor pool",
    },
    "playstation_room": {
        "uz": "PlayStation xonasi",
        "ru": "Комната PlayStation",
        "en": "PlayStation room",
    },
    "bicycles": {
        "uz": "Hududdagi velosipedlar",
        "ru": "Велосипеды на территории",
        "en": "Bicycles on site",
    },
    "hippotherapy": {"uz": "Ippoterapiya", "ru": "Иппотерапия", "en": "Hippotherapy"},
    "women_hairdresser": {
        "uz": "Ayollar sartaroshxonasi",
        "ru": "Парикмахерская для женщин",
        "en": "Women's hairdresser",
    },
    "kids_animators": {
        "uz": "Bolalar animatorlari",
        "ru": "Аниматоры для детей",
        "en": "Kids animators",
    },
    "nanny_service": {
        "uz": "Enaga xizmati",
        "ru": "Услуги няни",
        "en": "Nanny service",
    },
    "gym": {"uz": "Trenajyor zal", "ru": "Тренажёрный зал", "en": "Gym"},
    "billiards_tennis": {
        "uz": "Bilyard va stol tennisi",
        "ru": "Бильярд и настольный теннис",
        "en": "Billiards and table tennis",
    },
    "sports_fields": {
        "uz": "Sport maydonlari",
        "ru": "Спортивные площадки",
        "en": "Sports fields",
    },
    "cinema": {"uz": "Kinozal", "ru": "Кинотеатр", "en": "Cinema"},
    "doctor_observation": {
        "uz": "Shifokor ko'rigi va nazorati",
        "ru": "Осмотр и наблюдение врачей",
        "en": "Doctor check and observation",
    },
    "therapeutic_massage": {
        "uz": "Davolovchi massaj",
        "ru": "Лечебный массаж",
        "en": "Therapeutic massage",
    },
    "physiotherapy": {
        "uz": "Fizioterapevtik muolajalar",
        "ru": "Физиотерапевтические процедуры",
        "en": "Physiotherapy procedures",
    },
    "hydrotherapy": {
        "uz": "Gidroterapevtik muolajalar",
        "ru": "Гидротерапевтические процедуры",
        "en": "Hydrotherapy procedures",
    },
    "ozonotherapy": {"uz": "Ozonoterapiya", "ru": "Озонотерапия", "en": "Ozonotherapy"},
    "sauna_once": {
        "uz": "Yashash davomida 1 marta sauna",
        "ru": "Сауна 1 раз за проживание",
        "en": "Sauna once per stay",
    },
}

_POLICY_INCLUDE: dict[str, Label] = {
    "meals": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Meals"},
    "extra_mattress": {
        "uz": "Qo'shimcha matras",
        "ru": "Дополнительный матрас",
        "en": "Extra mattress",
    },
    "bedding": {
        "uz": "Yotoq anjomlari",
        "ru": "Постельные принадлежности",
        "en": "Bedding",
    },
}


def stay_meta() -> dict[str, list[Option]]:
    return {
        "stay_durations": from_labels(_STAY_DURATION),
        "stay_program_categories": from_labels(_STAY_PROGRAM_CATEGORY),
        "stay_program_inclusions": from_labels(_STAY_PROGRAM_INCLUSION),
        "policy_includes": from_labels(_POLICY_INCLUDE),
    }
