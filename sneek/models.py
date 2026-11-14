from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Deal:
    source: str           # z. B. "shopify:shoepalace.com"
    title: str
    url: str
    price: float | None = None
    old_price: float | None = None
    currency: str = ""
    size: str = ""         # gefundene Größe, leer = unbekannt
    size_verified: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def discount_percent(self) -> float | None:
        if not self.price or not self.old_price or self.old_price <= self.price:
            return None
        return round((1 - self.price / self.old_price) * 100, 1)

    @property
    def key(self) -> str:
        return self.extra.get("key") or f"{self.source}|{self.url}|{self.size}"

    def format(self) -> str:
        lines = [f"🏀 {self.title}"]
        if self.price is not None:
            p = f"{self.price:.2f} {self.currency}".strip()
            if self.old_price:
                p += f" statt {self.old_price:.2f} {self.currency}".rstrip()
            if self.discount_percent:
                p += f"  (-{self.discount_percent:.0f}%)"
            lines.append(f"💶 {p}")
        if self.size:
            lines.append(f"📏 Größe {self.size}" + ("" if self.size_verified else " (bitte prüfen)"))
        elif not self.size_verified:
            lines.append("📏 Größe US 16 bitte im Shop prüfen")
        if self.note:
            lines.append(f"ℹ️ {self.note}")
        lines.append(f"🏪 {self.source}")
        lines.append(self.url)
        return "\n".join(lines)
