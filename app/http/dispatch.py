from urllib.parse import unquote, urlsplit

from app.http import admin as http_admin
from app.http import assets as http_assets
from app.http import health as http_health
from app.http import location as http_location
from app.http import observation_pages as http_observations
from app.http import public as http_public
from app.http import public_data as http_public_data
from app.http import rate_limit as http_rate_limit
from app.http import request_body as http_request_body
from app.http import responses as http_responses
from app.http import retention as http_retention
from app.http import routes as http_routes
from app.http import settings as http_settings
from app.http import static_files as http_static_files
from app.http import wms_proxy as http_wms_proxy


def handle_options(handler) -> None:
    handler.send_response(204)
    handler.send_header("Content-Length", "0")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Request-ID", http_responses.request_id(handler))
    handler.end_headers()


def handle_head(handler) -> bool:
    path = unquote(urlsplit(handler.path).path)
    if http_observations.handle_public_route(handler, path, include_body=False):
        return True
    if http_static_files.handle_web_page(handler, path, include_body=False):
        return True
    if http_static_files.handle_web_asset(handler, path, include_body=False):
        return True
    if path.startswith("/api/"):
        handler._suppress_response_body = True
        try:
            if http_rate_limit.reject_limited(handler, "GET", path):
                return True
            if handle_static_api_get(handler, path):
                return True
            if handle_dynamic_api_get(handler, path):
                return True
            http_responses.send_api_not_found(handler, include_body=False)
            return True
        finally:
            del handler._suppress_response_body
    return False


def handle_static_api_get(handler, path: str) -> bool:
    handlers = {
        "/api/health/live": lambda: http_health.handle_liveness(handler),
        "/api/health/ready": lambda: http_health.handle_readiness(handler),
        "/api/admin/status": lambda: http_admin.handle_admin_status(handler),
        "/api/admin/photos": lambda: http_admin.handle_admin_photos(handler),
        "/api/admin/privacy-requests": lambda: http_admin.handle_admin_privacy_requests(handler),
        "/api/admin/photo-retention": lambda: http_admin.handle_photo_retention_status(
            handler, http_retention.snapshot()
        ),
        "/api/settings": lambda: http_settings.handle_get_settings(handler),
        "/api/address/reverse": lambda: http_public_data.handle_reverse_address(handler),
        "/api/cadastral/identify": lambda: http_public_data.handle_cadastral_identify(handler),
        "/api/field-photos": lambda: http_public_data.handle_field_photos(handler),
    }
    route_handler = handlers.get(path)
    if route_handler is None:
        return False
    route_handler()
    return True


def handle_dynamic_api_get(handler, path: str) -> bool:
    route_handlers = (
        (http_routes.admin_photo_original_route, http_assets.handle_admin_photo_original),
        (http_routes.field_photo_asset_route, http_assets.handle_field_photo_asset),
    )
    for route_from_path, route_handler in route_handlers:
        route = route_from_path(path)
        if route:
            route_handler(handler, route)
            return True
    return False


def handle_passthrough_get(handler, path: str) -> bool:
    if handler.path.startswith("/wms_proxy/"):
        http_wms_proxy.handle_wms_proxy(handler)
        return True
    if handler.path.startswith("/tile_proxy/"):
        http_wms_proxy.handle_geoportal_tile_proxy(handler)
        return True
    return False


def handle_get(handler) -> bool:
    path = unquote(urlsplit(handler.path).path)
    if http_rate_limit.reject_limited(handler, "GET", path):
        return True
    if http_observations.handle_public_route(handler, path):
        return True
    if http_static_files.handle_web_page(handler, path):
        return True
    if http_static_files.handle_web_asset(handler, path):
        return True
    if handle_static_api_get(handler, path):
        return True
    if handle_dynamic_api_get(handler, path):
        return True
    if handle_passthrough_get(handler, path):
        return True
    if path.startswith("/api/"):
        http_responses.send_api_not_found(handler)
        return True
    return False


def handle_delete(handler) -> None:
    if http_request_body.reject_unsafe_request(handler):
        return
    request_path = unquote(urlsplit(handler.path).path)
    admin_photo_delete_route = http_routes.admin_photo_delete_route(request_path)
    if admin_photo_delete_route:
        http_admin.handle_delete_admin_photo(handler, admin_photo_delete_route)
        return

    http_responses.send_api_not_found(handler)


def handle_patch(handler) -> None:
    if http_request_body.reject_unsafe_request(handler):
        return
    request_path = unquote(urlsplit(handler.path).path)
    if http_rate_limit.reject_limited(handler, "PATCH", request_path):
        return

    admin_photo_review_route = http_routes.admin_photo_review_route(request_path)
    if admin_photo_review_route:
        http_request_body.dispatch_json_request(
            handler, http_admin.handle_review_photo, handler, admin_photo_review_route
        )
        return

    field_photo_location_route = http_routes.field_photo_location_route(request_path)
    if field_photo_location_route:
        http_request_body.dispatch_json_request(
            handler, http_admin.handle_update_field_photo_location, handler, field_photo_location_route
        )
        return

    field_photo_owner_review_route = http_routes.field_photo_owner_review_route(request_path)
    if field_photo_owner_review_route:
        http_request_body.dispatch_json_request(
            handler, http_public.handle_owner_review_field_photo, handler, field_photo_owner_review_route
        )
        return

    admin_privacy_request_route = http_routes.admin_privacy_request_route(request_path)
    if admin_privacy_request_route:
        http_request_body.dispatch_json_request(
            handler, http_admin.handle_update_privacy_request, handler, admin_privacy_request_route
        )
        return

    http_responses.send_api_not_found(handler)


def handle_post(handler) -> None:
    if http_request_body.reject_unsafe_request(handler):
        return
    request_path = unquote(urlsplit(handler.path).path)
    if http_rate_limit.reject_limited(handler, "POST", request_path):
        return
    if request_path == "/api/admin/login":
        http_request_body.dispatch_json_request(handler, http_admin.handle_admin_login, handler)
        return
    if request_path == "/api/admin/logout":
        http_admin.handle_admin_logout(handler)
        return
    if request_path == "/api/privacy-requests":
        http_request_body.dispatch_json_request(handler, http_public.handle_create_privacy_request, handler)
        return
    if request_path == "/api/field-photos/owner-claim":
        http_request_body.dispatch_json_request(handler, http_public.handle_claim_field_photos, handler)
        return
    if request_path == "/api/field-photos/owner-submit":
        http_request_body.dispatch_json_request(handler, http_public.handle_submit_field_photos, handler)
        return
    if request_path == "/api/field-photos/owner-discard":
        http_request_body.dispatch_json_request(handler, http_public.handle_discard_field_photo_drafts, handler)
        return
    if request_path == "/api/field-photos/owner-delete":
        http_request_body.dispatch_json_request(handler, http_public.handle_delete_field_photos_by_owner, handler)
        return
    if request_path == "/api/admin/photo-retention/run":
        http_request_body.dispatch_json_request(handler, http_retention.handle_run_photo_retention, handler)
        return
    if request_path == "/api/field-photo-reports/report-pdf":
        if http_request_body.reject_wrong_content_type(handler, "multipart/form-data"):
            return
        http_public.handle_field_photo_report_pdf(handler)
        return
    field_photo_owner_original_route = http_routes.field_photo_owner_original_route(request_path)
    if field_photo_owner_original_route:
        http_request_body.dispatch_json_request(
            handler, http_public.handle_field_photo_owner_original, handler, field_photo_owner_original_route
        )
        return
    if request_path == "/api/field-photos":
        if http_request_body.reject_wrong_content_type(handler, "multipart/form-data"):
            return
        http_public.handle_create_field_photo(handler)
        return
    if request_path == "/api/settings":
        http_request_body.dispatch_json_request(handler, http_settings.handle_save_settings, handler)
        return
    if request_path == "/api/inspect":
        http_request_body.dispatch_json_request(handler, http_location.handle_inspect, handler)
        return
    http_responses.send_api_not_found(handler)
