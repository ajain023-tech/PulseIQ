"""All tunable knobs of the simulation, plus the planted experiment truths.

Every behavioural assumption in the generator lives here as a documented number so
it can be inspected, tuned and written verbatim into ``ground_truth.json``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

COUNTRIES = {
    # country: (tier, share of signups)
    "US": ("high", 0.24),
    "UK": ("high", 0.09),
    "DE": ("high", 0.07),
    "FR": ("mid", 0.06),
    "CA": ("mid", 0.06),
    "ES": ("mid", 0.05),
    "IN": ("low", 0.22),
    "BR": ("low", 0.12),
    "ID": ("low", 0.09),
}
PLATFORMS = {"ios": 0.40, "android": 0.45, "web": 0.15}
CHANNELS = {
    "organic": 0.33,
    "paid_social": 0.25,
    "search": 0.20,
    "referral": 0.10,
    "influencer": 0.12,
}
DEVICE_TIERS = ("low", "mid", "high")
FEATURES = ("workout_log", "plan_view", "progress_chart", "social_share", "reminder_set")
CANCEL_REASONS = ("too_expensive", "not_using", "found_alternative", "technical_issues", "other")


@dataclass(frozen=True)
class EngagementParams:
    """Latent engagement z = logit(Beta(a, b)) + segment shifts."""

    beta_a: float = 2.2
    beta_b: float = 2.8
    channel_shift: dict = field(
        default_factory=lambda: {
            "organic": 0.25,
            "paid_social": -0.45,
            "search": 0.05,
            "referral": 0.55,
            "influencer": -0.15,
        }
    )
    platform_shift: dict = field(
        default_factory=lambda: {"ios": 0.15, "android": -0.05, "web": -0.25}
    )
    device_shift: dict = field(default_factory=lambda: {"low": -0.35, "mid": 0.0, "high": 0.2})
    country_tier_shift: dict = field(default_factory=lambda: {"high": 0.1, "mid": 0.0, "low": -0.1})
    # Device-tier mix per platform (low, mid, high).
    device_mix: dict = field(
        default_factory=lambda: {
            "ios": (0.10, 0.45, 0.45),
            "android": (0.40, 0.40, 0.20),
            "web": (0.20, 0.50, 0.30),
        }
    )


@dataclass(frozen=True)
class SignupParams:
    """Arrival process: weekday seasonality and a marketing spike week."""

    weekday_multiplier: tuple = (1.15, 1.05, 1.0, 1.0, 0.95, 0.80, 0.90)  # Mon..Sun
    spike_start_frac: float = 0.35  # spike week starts at 35 % of the date range
    spike_days: int = 7
    spike_multiplier: float = 1.6
    app_versions: tuple = ("3.0", "3.1", "3.2", "3.3", "3.4")


@dataclass(frozen=True)
class OnboardingParams:
    """5-step onboarding funnel; completion = sigmoid(intercept + slope * z)."""

    intercept: float = 0.50
    slope: float = 0.9
    # Where non-completers drop: probability they abandon at step 1..5.
    drop_step_probs: tuple = (0.34, 0.25, 0.18, 0.13, 0.10)


@dataclass(frozen=True)
class ActivityParams:
    """Daily activity model.

    Days are 24 h blocks after ``signup_ts`` (block 0 = signup day).
    * Blocks 1–2: active with prob sigmoid(early_intercept + early_slope * z).
    * From block 3: the user is "alive" until a latent churn time with cumulative
      hazard m_u * base_hazard * (d - 2) ** hazard_shape, and while alive is active
      each day with prob sigmoid(alive_intercept + alive_slope * z).
    * log m_u = -hazard_z * z - reminder_effect * [reminder_set in 72 h]
      - workout_effect * min(workout_log in 72 h, workout_cap)
      - early_days_effect * (#active blocks among 1–2).
    """

    early_intercept: float = -0.18
    early_slope: float = 0.9
    alive_intercept: float = 0.35
    alive_slope: float = 0.6
    base_hazard: float = 1.55
    hazard_shape: float = 0.32
    hazard_z: float = 0.55
    reminder_effect: float = 0.70
    workout_effect: float = 0.10
    workout_cap: int = 8
    early_days_effect: float = 0.35
    sessions_base: float = 0.25  # extra sessions per active day ~ Poisson(base + slope*eng)
    sessions_slope: float = 0.6
    events_base: float = 2.5  # middle events per session ~ Poisson(base + slope*eng)
    events_slope: float = 3.0
    max_events_per_session: int = 15


@dataclass(frozen=True)
class MonetizationParams:
    """Trial and subscription economics."""

    trial_intercept: float = -0.92
    trial_slope: float = 0.7
    trial_tier_shift: dict = field(default_factory=lambda: {"high": 0.0, "mid": 0.0, "low": -0.2})
    trial_day0_share: float = 0.6  # otherwise on a later active day within 14 days
    trial_window_days: int = 14
    trial_length_days: int = 7
    paid_intercept: float = 0.22
    paid_slope: float = 0.6
    paid_tier_shift: dict = field(default_factory=lambda: {"high": 0.15, "mid": 0.0, "low": -0.25})
    annual_share: float = 0.25
    price_monthly: dict = field(default_factory=lambda: {"high": 9.99, "mid": 6.99, "low": 3.99})
    price_annual: dict = field(default_factory=lambda: {"high": 59.99, "mid": 41.99, "low": 23.99})
    renewal_days: int = 30
    cancel_prob_active_user: float = 0.08
    cancel_prob_churned_user: float = 0.45
    annual_cancel_prob: float = 0.05
    refund_rate: float = 0.03


@dataclass(frozen=True)
class ExperimentSpec:
    """A planted experiment. Day windows are for the 120-day full size and are
    scaled proportionally for other sizes."""

    experiment_id: str
    name: str
    hypothesis: str
    start_day: int
    end_day: int
    population: str
    primary_metric: str
    guardrail_metrics: tuple
    secondary_metrics: tuple
    allocation: float = 0.5


EXPERIMENTS: tuple[ExperimentSpec, ...] = (
    ExperimentSpec(
        experiment_id="onboarding_flow_v2",
        name="Onboarding flow v2 (shorter flow)",
        hypothesis="A shorter onboarding flow increases onboarding completion without hurting paid conversion.",
        start_day=30,
        end_day=75,
        population="new signups during the test window, assigned 50/50 at signup",
        primary_metric="onboarding_completed",
        guardrail_metrics=("paid_30d", "d30_retained"),
        secondary_metrics=("trial_started_14d", "d1_retained", "d7_retained"),
    ),
    ExperimentSpec(
        experiment_id="paywall_redesign",
        name="Paywall redesign (re-engagement campaign)",
        hypothesis="A redesigned paywall raises trial starts among existing free users.",
        start_day=80,
        end_day=110,
        population="existing free users with >= 14 days tenure and a session in the 28 days before start",
        primary_metric="trial_started_in_test",
        guardrail_metrics=("refund_in_test",),
        secondary_metrics=("paid_in_test", "sessions_in_test", "net_revenue_in_test"),
    ),
    ExperimentSpec(
        experiment_id="streak_reminder",
        name="Daily streak reminder push",
        hypothesis="A daily streak reminder improves week-1 retention.",
        start_day=60,
        end_day=100,
        population="new signups during the test window, assigned 50/50 at signup",
        primary_metric="d7_retained",
        guardrail_metrics=("d1_retained",),
        secondary_metrics=("d30_retained", "trial_started_14d", "paid_30d"),
    ),
)


@dataclass(frozen=True)
class PlantedEffects:
    """Effects the generator plants; the realised truth is computed exactly."""

    onboarding_completion_pp: float = 0.030
    onboarding_paid_pp: float = -0.005
    paywall_trial_relative: float = 0.08
    paywall_trial_intercept: float = 0.0
    paywall_trial_per_session: float = 0.045
    paywall_trial_cap: float = 0.88
    streak_d7_pp: float = 0.015
    # Planted bug: share of *all* treatment users that are lost from the assignment
    # log; the loss happens only on Android, so Android treatment loses ~13 %.
    streak_srm_treatment_loss: float = 0.06


@dataclass(frozen=True)
class DirtParams:
    """Realistic data-quality issues injected at low rates."""

    duplicate_event_rate: float = 0.003
    clock_skew_rate: float = 0.002
    null_platform_rate: float = 0.0005


@dataclass(frozen=True)
class GeneratorParams:
    """Bundle of every parameter group."""

    engagement: EngagementParams = field(default_factory=EngagementParams)
    signup: SignupParams = field(default_factory=SignupParams)
    onboarding: OnboardingParams = field(default_factory=OnboardingParams)
    activity: ActivityParams = field(default_factory=ActivityParams)
    monetization: MonetizationParams = field(default_factory=MonetizationParams)
    effects: PlantedEffects = field(default_factory=PlantedEffects)
    dirt: DirtParams = field(default_factory=DirtParams)

    def to_dict(self) -> dict:
        """JSON-serialisable view of every parameter."""
        return asdict(self)


TRUE_RETENTION_DRIVERS = (
    {
        "feature": "reminder_set_72h",
        "direction": "+",
        "mechanism": "setting a reminder in the first 72 h multiplies the churn hazard by exp(-reminder_effect)",
    },
    {
        "feature": "workout_log_72h",
        "direction": "+",
        "mechanism": "each workout_log in the first 72 h (capped) lowers the churn hazard by workout_effect on the log scale",
    },
    {
        "feature": "active_days_72h",
        "direction": "+",
        "mechanism": "each active day among days 1-2 lowers the churn hazard by early_days_effect on the log scale",
    },
    {
        "feature": "latent engagement (proxied by sessions/events in 72 h, channel, platform, device tier)",
        "direction": "+",
        "mechanism": "higher engagement lowers hazard and raises daily activity probability",
    },
)
