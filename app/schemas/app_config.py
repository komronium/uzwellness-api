from pydantic import BaseModel, Field

# --- /admin/config -----------------------------------------------------------


class CommissionOverride(BaseModel):
    region: str = Field(max_length=100)
    rate: float = Field(ge=0, le=100)


class CommissionConfig(BaseModel):
    global_rate: float = Field(default=0.0, ge=0, le=100)
    overrides: list[CommissionOverride] = Field(default_factory=list, max_length=50)


class PaymentGatewaysConfig(BaseModel):
    stripe: bool = True
    payme: bool = True
    click: bool = True


class EmailTemplate(BaseModel):
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=20_000)


class EmailTemplatesConfig(BaseModel):
    booking_confirmed: EmailTemplate = Field(default_factory=EmailTemplate)
    booking_cancelled: EmailTemplate = Field(default_factory=EmailTemplate)


class FeatureFlags(BaseModel):
    maintenance_mode: bool = False
    new_registrations: bool = True
    b2b_portal: bool = True
    flight_module: bool = True
    train_module: bool = True
    reviews_enabled: bool = True


class AdminConfig(BaseModel):
    commission: CommissionConfig = Field(default_factory=CommissionConfig)
    payment_gateways: PaymentGatewaysConfig = Field(
        default_factory=PaymentGatewaysConfig
    )
    email_templates: EmailTemplatesConfig = Field(default_factory=EmailTemplatesConfig)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)


# --- /admin/homepage-config --------------------------------------------------


class HeroSlide(BaseModel):
    id: str = Field(max_length=64)
    video: str = Field(default="", max_length=1000)
    poster: str = Field(default="", max_length=1000)
    enabled: bool = True


class TrustStats(BaseModel):
    sanatoriums: str = Field(default="200+", max_length=32)
    countries: str = Field(default="47", max_length=32)
    rating: str = Field(default="4.8", max_length=32)
    savings: str = Field(default="Up to 60%", max_length=32)


class SectionVisibility(BaseModel):
    trust_bar: bool = True
    why_uzbekistan: bool = True
    destinations: bool = True
    treatments: bool = True
    featured_sanatoriums: bool = True
    packages: bool = True
    how_it_works: bool = True
    testimonials: bool = True
    b2b: bool = True


class HomepageConfig(BaseModel):
    hero_slides: list[HeroSlide] = Field(default_factory=list, max_length=20)
    trust_stats: TrustStats = Field(default_factory=TrustStats)
    section_visibility: SectionVisibility = Field(default_factory=SectionVisibility)
