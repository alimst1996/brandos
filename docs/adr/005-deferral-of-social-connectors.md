# ADR-005: Deferral of Social Connectors

## Status

Accepted

## Date

2026-07-24

## Context

The original BrandOS vision includes social media engagement features:
monitoring mentions, posting content, responding to comments, and tracking
engagement metrics across platforms (Instagram, X/Twitter, Telegram).

Building social connectors requires:
- OAuth integration with each platform's API
- Handling platform-specific rate limits and content formats
- Webhook infrastructure for real-time event processing
- Content moderation and compliance for each platform
- Significant ongoing maintenance as platforms change their APIs

The MVP phase (v0.1 Foundation) should focus on the autonomous delivery
pipeline and brand intelligence data model. Social features are a
value-add layer that depends on these foundations being solid.

## Decision

**Defer all social media connectors to post-MVP (v0.2 or later).**

In the MVP:
- BrandOS generates content (text, images, video) that is brand-voice aligned.
- Generated content is stored in the platform and can be downloaded or
  copy-pasted by the brand owner.
- The `brandossocial` agent profile exists in the team structure but has
  no active work in the foundation phase.
- No OAuth flows, API integrations, or webhook handlers for social platforms
  are built.

When social connectors are prioritized (post-MVP):
- Each platform connector gets its own ADR.
- Connectors are implemented as isolated modules with a shared interface
  (`SocialConnector` abstract class).
- The agent team can work on connectors in parallel since they are independent.

## Consequences

### Positive

- MVP scope is significantly reduced (weeks of OAuth/API work avoided).
- The autonomous delivery pipeline and brand intelligence get full attention.
- No dependency on third-party API stability for the MVP launch.
- The social agent profile is ready to be activated without team restructuring.

### Negative

- BrandOS MVP has no automated posting — the brand owner must manually
  post generated content.
- Engagement monitoring is not available in the MVP.
- Competitors with social features may have an advantage.

### Neutral

- This is a scope decision, not an architecture decision. The codebase
  is structured to add connectors later without refactoring.
- The `brandossocial` profile remains in the agent team roster so that
  Jira issues can be labeled for future social work.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Build Instagram connector only | Partial support creates maintenance burden without full value |
| Use a third-party social API (Buffer, Hootsuite) | Adds dependency and cost; doesn't leverage BrandOS's brand voice engine |
| Build connectors in parallel with MVP | Doubles the scope; delays the foundation phase |

## Links

- Related ADRs: None
- Related Jira issues: EPIC-004 (Social Connectors — deferred)
- Vision reference: [Product Vision §4.3](../vision.md#43-social-engagement)
