"""Machine-readable API contract for AI clients; informational, no execution."""

from app.http import responses as http_responses

OPENAPI = {
    "openapi": "3.0.3",
    "info": {
        "title": "IleStoi.pl — AI report preparation",
        "version": "1.0.0",
        "description": (
            "Read public, moderated vehicle evidence and generate a PDF draft. "
            "No endpoint sends an email or files a report with an authority. "
            "An address, color, or natural-language description is not a unique vehicle identifier; "
            "select and verify photo_ids and group coordinates before generating. "
            "Never invent observations, reporter contact details or a date."
        ),
    },
    "servers": [{"url": "https://ilestoi.pl"}],
    "paths": {
        "/api/field-photos": {
            "get": {
                "operationId": "listPublicFieldPhotos",
                "summary": "Find public photo candidates in a map bounding box",
                "description": (
                    "Returns only data allowed by public map visibility settings; "
                    "pending/nonvehicle items may occur. Paginate via next_cursor. "
                    "Select a single approved active vehicle group and verify its photos."
                ),
                "parameters": [
                    {
                        "name": "bbox",
                        "in": "query",
                        "required": True,
                        "description": "west,south,east,north in WGS84; narrow search bounds",
                        "schema": {"type": "string", "example": "17.031,51.089,17.039,51.096"},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                    },
                    {"name": "cursor", "in": "query", "required": False, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "Public photo records; pagination cursor when limit is supplied",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string"},
                                        "photos": {"type": "array", "items": {"type": "object"}},
                                        "next_cursor": {"type": "string", "nullable": True},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Invalid query parameters"},
                },
            }
        },
        "/api/ai/report-pdf": {
            "post": {
                "operationId": "generateVehicleReportPdf",
                "summary": "Generate a downloadable PDF draft from approved photo IDs",
                "description": (
                    "No persistent case is created, and no email is sent. "
                    "Uses the same moderation, same-group, active-vehicle, coordinate, "
                    "photo-byte and concurrency checks as the website generator. "
                    "Requires server-to-server HTTP or an allowed same-origin browser request; "
                    "cross-site browser mutations are blocked. Rate limits and the "
                    "public report feature toggle still apply. Avoid retry loops."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "photo_ids",
                                    "lat",
                                    "lon",
                                    "reporter_name",
                                    "reporter_email",
                                    "reporter_phone",
                                    "reporter_address",
                                    "location_description",
                                    "observed_at",
                                    "vehicle_description",
                                ],
                                "properties": {
                                    "photo_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                                    "lat": {"type": "number", "description": "Group latitude in WGS84"},
                                    "lon": {"type": "number", "description": "Group longitude in WGS84"},
                                    "reporter_name": {"type": "string", "maxLength": 120},
                                    "reporter_email": {"type": "string", "maxLength": 160},
                                    "reporter_phone": {"type": "string", "maxLength": 80},
                                    "reporter_address": {"type": "string", "maxLength": 240},
                                    "location_description": {"type": "string", "maxLength": 1200},
                                    "observed_at": {
                                        "type": "string",
                                        "description": "Actual observation time, YYYY-MM-DDTHH:MM",
                                    },
                                    "vehicle_description": {"type": "string", "maxLength": 2000},
                                    "crop_m": {"type": "number", "enum": [5, 7.5, 10, 15, 20], "default": 7.5},
                                },
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Generated PDF draft encoded in response JSON",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["ok"]},
                                        "pdf_filename": {"type": "string"},
                                        "pdf_base64": {"type": "string", "format": "byte"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Invalid selection or form"},
                    "403": {"description": "Disabled feature or disallowed origin"},
                    "404": {"description": "Photo unavailable"},
                    "413": {"description": "Body exceeds limit"},
                    "415": {"description": "JSON content type required"},
                    "429": {"description": "Rate limit"},
                    "503": {"description": "Report concurrency limit"},
                },
            }
        },
    },
}


def handle_openapi(handler) -> None:
    http_responses.send_json(handler, 200, OPENAPI)
