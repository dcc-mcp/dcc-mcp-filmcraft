"""FilmCraft Core/MCP browser and native-engine adapter."""

__version__ = "0.1.0"


def __getattr__(name):
    if name == "FilmCraftAdapter":
        from .adapter import FilmCraftAdapter

        return FilmCraftAdapter
    raise AttributeError(name)
