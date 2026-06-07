from enum import StrEnum

type Label = dict[str, str]
type Option = dict[str, str | Label]


def default_label(value: str) -> Label:
    text = value.replace("_", " ").title()
    return {"uz": text, "ru": text, "en": text}


def from_labels(labels: dict[str, Label]) -> list[Option]:
    return [{"value": value, "label": label} for value, label in labels.items()]


def from_enum(enum_cls: type[StrEnum], labels: dict[str, Label]) -> list[Option]:
    return [
        {
            "value": item.value,
            "label": labels.get(item.value, default_label(item.value)),
        }
        for item in enum_cls
    ]
