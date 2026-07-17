# Experience Catalog and UI Extensions

## Catalog model

Templates, skill packs, design systems and editor profiles are user-visible Experiences. A mutable display entry points to an immutable revision; every WorkOrder and RunManifest stores the selected revision digest.

```text
ExperienceCatalogEntry
 -> current immutable TemplateRevision
 -> certified ProviderRevision
 -> source/preview ArtifactVersion
 -> parameter SchemaReference
```

Catalog discovery is filtered by tenant/client binding, lifecycle, Capability and the Business-signed commercial authorization. A hidden or unauthorized entry cannot be selected by sending its ID directly.

Run admission rechecks Scenario `required_tags`, TemplateRevision `required_entitlements` and the explicit entitlement set in `CommercialAuthorizationSnapshot`; Catalog filtering alone is not an authorization boundary.

Scenario UI uses a signed UI Schema and typed option sources. Fields such as `/template_id` query the Experience Catalog; they never hard-code Plugin IDs.

## nexu-io integration profiles

- html-anything template/skill folders: Catalog importer plus Template Provider.
- html-anything generation: Skill or sandbox_cli/MCP capability under DeerFlow.
- html-to-pptx/html-video: Converter Provider producing Artifact Staging.
- Open Design/motion-anything editors: Artifact Editor/Renderer Provider; reuse headless capability and catalog assets before embedding UI.
- complete desktop applications are not mounted wholesale into the stable kernel.

Each upstream project is pinned by source commit/package digest, license/provenance, Adapter version and Conformance evidence. Upgrades create new Provider and Experience revisions; existing Runs keep old snapshots.

## UI extension security

Schema-driven UI is preferred. A richer contribution requires a certified `UiExtensionManifest`:

- signed immutable bundle Artifact;
- fixed platform slot and `ui-extension/v1` message protocol;
- opaque-origin sandboxed iframe and approved CSP profile;
- object-scoped Artifact/Catalog grants;
- no WorkSession cookie, raw token, host DOM or arbitrary network access.

Arbitrary remote JavaScript remains forbidden.
