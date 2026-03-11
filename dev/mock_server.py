from __future__ import annotations
from typing import Any
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="mock-xray-archive",
    instructions=(
        "You are a mock X-ray astronomy archive assistant. "
        "You have access to simulated observation data for testing."
    ),
    host="0.0.0.0",
    port=9000,
)

@mcp.tool(name="search_observations", description="Search for X-ray observations by target name or coordinates.")
def search_observations(target: str, radius_arcmin: float = 5.0) -> dict[str, Any]:
    return {
        "target": target,
        "radius_arcmin": radius_arcmin,
        "results": [
            {"obsid": "12345", "target": target, "exposure_ks": 50.0, "instrument": "ACIS-S", "date": "2024-01-15"},
            {"obsid": "67890", "target": target, "exposure_ks": 30.0, "instrument": "ACIS-I", "date": "2023-06-22"},
        ],
    }

@mcp.tool(name="get_observation_details", description="Get detailed metadata for a specific observation by ObsID.")
def get_observation_details(obsid: str) -> dict[str, Any]:
    return {
        "obsid": obsid,
        "target": "Cas A",
        "ra": 350.866,
        "dec": 58.815,
        "exposure_ks": 50.0,
        "instrument": "ACIS-S",
        "grating": "NONE",
        "date": "2024-01-15",
        "pi": "Dr. Example",
        "status": "archived",
    }

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
