# Module: config

---
status: in-progress
priority: P0
---

## Responsibility

Configuration loading, validation, and resource profile management.

**In scope:**
- YAML config file parsing
- Resource profile selection (minimal/standard/performance)
- Path resolution (XDG directories)
- Environment variable overrides
- Validation and defaults

**Out of scope:**
- Live config reloading (restart required)
- Remote configuration management
- Secrets management (use environment or keyring)

## Interface

### Public API

```python
from orthrus.config import Config, ResourceProfile, load_config

class ResourceProfile(Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    PERFORMANCE = "performance"

class Config:
    """Validated configuration."""
    
    profile: ResourceProfile
    capture: CaptureConfig
    storage: StorageConfig
    embedding: Optional[EmbeddingConfig]
    search: SearchConfig
    sync: Optional[SyncConfig]
    
    @classmethod
    def from_file(cls, path: Path) -> "Config": ...
    
    @classmethod
    def default(cls) -> "Config": ...

def load_config(path: Optional[Path] = None) -> Config:
    """
    Load config from path or search default locations.
    Search order:
    1. Explicit path
    2. ~/.orthrus/config.yaml
    3. ~/.config/orthrus/config.yaml (XDG)
    4. Default configuration
    """
    ...

class ValidationError(Exception): ...
```

### CLI

```bash
orthrus config init           # Create default config
orthrus config validate       # Check current config
orthrus config show           # Display effective config
```

## Dependencies

- **external**: pydantic (validation), platformdirs (XDG paths)

## Resource Contract

- Config loading is synchronous and fast (<100ms)
- Validation errors are descriptive and actionable

## Error Handling

| Error | Response |
|-------|----------|
| Invalid YAML | Clear error with line number |
| Unknown field | Warning or error (strict mode) |
| Missing required | Error with default suggestion |
| Invalid profile | Error with valid options |

## Testing

- Unit: All default configs load and validate
- Unit: Invalid configs produce clear errors
- Integration: File search order works
