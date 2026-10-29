// Centralna konfiguracja frontendu. Zmiany tutaj wpływają tylko na zachowanie
// przeglądarki; limity bezpieczeństwa backendu są osobno egzekwowane w Pythonie.

function normalizeDefaultMapView(raw, fallback) {
    const lat = Number(raw?.lat);
    const lon = Number(raw?.lon);
    const zoom = Number(raw?.zoom);
    if (
        Number.isFinite(lat) && lat >= -90 && lat <= 90 &&
        Number.isFinite(lon) && lon >= -180 && lon <= 180 &&
        Number.isFinite(zoom) && zoom >= 0 && zoom <= 22
    ) {
        return { center: [lat, lon], zoom: Math.round(zoom) };
    }
    return { center: [...fallback.center], zoom: fallback.zoom };
}

function setDefaultMapView(raw) {
    DEFAULT_MAP_VIEW = normalizeDefaultMapView(raw, STATIC_DEFAULT_MAP_VIEW);
}

// Klucze localStorage. Zmiana nazwy resetuje zapisane preferencje użytkownika.
const MAP_VIEW_STORAGE_KEY = 'wreckscanner.mapView.v3';
const ENHANCEMENT_SETTINGS_STORAGE_KEY = 'wreckscanner.enhancementSettings.v2';
const MAP_SOURCE_SLIDER_VISIBLE_STORAGE_KEY = 'wreckscanner.mapSourceSliderVisible.v1';
const VEHICLE_STANDING_FILTER_DAYS_STORAGE_KEY = 'wreckscanner.vehicleStandingFilterDays.v1';
const VEHICLE_RESOLUTION_FILTER_STORAGE_KEY = 'wreckscanner.vehicleResolutionFilter.v1';
const CADASTRAL_LAYER_VISIBLE_STORAGE_KEY = 'wroclaw-ortho-cadastral-visible';

// Endpointy są relatywne, żeby aplikacja działała przez tunel/proxy bez
// twardego hosta i portu w JS.
const SETTINGS_URL = '/api/settings';
const FIELD_PHOTOS_URL = '/api/field-photos';
const ADDRESS_REVERSE_URL = '/api/address/reverse';
const CADASTRAL_IDENTIFY_URL = '/api/cadastral/identify';
const ADMIN_STATUS_URL = '/api/admin/status';
const ADMIN_LOGIN_URL = '/api/admin/login';
const ADMIN_LOGOUT_URL = '/api/admin/logout';
const ADMIN_PHOTOS_URL = '/api/admin/photos';
const ADMIN_PRIVACY_REQUESTS_URL = '/api/admin/privacy-requests';
const ADMIN_PHOTO_RETENTION_URL = '/api/admin/photo-retention';

const PUBLIC_LAYER_KEYS = {
    vehicles: 'vehicles',
    fieldPhotoInfrastructure: 'field_photo_infrastructure',
    fieldPhotoSmoke: 'field_photo_smoke',
    fieldPhotoPending: 'field_photo_pending',
    cadastral: 'cadastral',
    baseMapOsm: 'base_map_osm',
};

const PUBLIC_FEATURE_KEYS = {
    reportPdfs: 'report_pdfs',
    photoUploads: 'photo_uploads',
};

// Źródła podkładu mapy w UI; frontend steruje tutaj wyłącznie podglądem w Leaflet.
const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const STREET_LABELS_WMS_URL = 'https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaNumeracjiAdresowej';
const GEOPORTAL_STANDARD_TILE_PROXY_URL =
    '/tile_proxy/geoportal-standard/{z}/{x}/{y}?enhancementSettings={enhancementSettings}';
const MAP_SOURCES = [
    { key: 'wroclaw-2020', shortLabel: '2020', label: 'Wrocław 2020', type: 'wroclaw', year: 2020 },
    { key: 'wroclaw-2021', shortLabel: '2021', label: 'Wrocław 2021', type: 'wroclaw', year: 2021 },
    { key: 'wroclaw-2022', shortLabel: '2022', label: 'Wrocław 2022', type: 'wroclaw', year: 2022 },
    { key: 'wroclaw-2023', shortLabel: '2023', label: 'Wrocław 2023', type: 'wroclaw', year: 2023 },
    { key: 'wroclaw-2024', shortLabel: '2024', label: 'Wrocław 2024', type: 'wroclaw', year: 2024 },
    { key: 'wroclaw-2025', shortLabel: '2025', label: 'Wrocław 2025', type: 'wroclaw', year: 2025 },
    {
        key: 'openstreetmap',
        shortLabel: 'OSM',
        label: 'OpenStreetMap',
        type: 'tile',
        url: OSM_TILE_URL,
        maxNativeZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>',
        labelsOverlay: false,
        publicLayerKey: PUBLIC_LAYER_KEYS.baseMapOsm,
    },
    {
        key: 'poland-ortho',
        shortLabel: 'POL',
        label: 'Polska ortofoto',
        type: 'tile',
        url: GEOPORTAL_STANDARD_TILE_PROXY_URL,
        maxNativeZoom: 19,
        attribution: 'Geoportal.gov.pl / GUGiK',
    },
];
const DEFAULT_MAP_SOURCE_KEY = 'poland-ortho';
const CADASTRAL_WMS_URL = 'https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow';
const CADASTRAL_WMS_LAYERS = 'dzialki,numery_dzialek';
const STATIC_DEFAULT_MAP_VIEW = {
    center: [51.107883, 17.038538],
    zoom: 13,
};
const MAX_MAP_ZOOM = 22;
let DEFAULT_MAP_VIEW = normalizeDefaultMapView(window.WRECKSCANNER_APP_SETTINGS?.map_view, STATIC_DEFAULT_MAP_VIEW);
const METERS_PER_DEGREE_LAT = 111320;

// Przy dalekim oddaleniu pinezki przechodzą w małe klikane kropki.
// Do tego momentu zachowują liczniki zdjęć.
const MARKER_DETAIL_DOT_MAX_ZOOM = 16;
const MAP_POPUP_PREVIEW_MAX_IMAGES = 6;
const VEHICLE_LONG_STANDING_DEFAULT_DAYS = 30;
const VEHICLE_LONG_STANDING_DAY_OPTIONS = [30, 60, 90];

// Uploady: backend dalej waliduje te same limity, frontend tylko daje szybszy
// komunikat przed wysłaniem formularza.
const FIELD_PHOTO_MAX_BYTES = 10 * 1024 * 1024;
const FIELD_PHOTO_MAX_FILES = 25;
const FIELD_PHOTO_EDIT_TOKEN_MIN_LENGTH = 8;
const FIELD_PHOTO_EDIT_TOKEN_MAX_LENGTH = 80;
const FIELD_PHOTO_ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const UFG_OC_CHECK_URL = 'https://www.ufg.pl/';
const FIELD_PHOTO_ISSUE_TYPE_VEHICLE = 'vehicle';
const FIELD_PHOTO_ISSUE_TYPES = new Set([
    FIELD_PHOTO_ISSUE_TYPE_VEHICLE,
    'infrastructure',
    'smoke',
]);
const FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN = 'unknown';
const FIELD_PHOTO_VEHICLE_INSURANCE_STATUSES = new Set([
    FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN,
    'insured',
    'uninsured',
]);
const FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE = 'active';
const FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED = 'removed';
const FIELD_PHOTO_VEHICLE_RESOLUTION_STATUSES = new Set([
    FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE,
    FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED,
]);
const FIELD_PHOTO_PUBLIC_LAYER_KEYS = {
    vehicle: PUBLIC_LAYER_KEYS.vehicles,
    infrastructure: PUBLIC_LAYER_KEYS.fieldPhotoInfrastructure,
    smoke: PUBLIC_LAYER_KEYS.fieldPhotoSmoke,
};

// Grupowanie zdjęć terenowych na mapie. 1 m jest celowo ciasne: większy promień
// scalał zdjęcia z sąsiednich pojazdów albo różnych stron tego samego parkingu.
const FIELD_PHOTO_GROUP_RADIUS_M = 1;

// Timery UI. Krótsze wartości dają szybszą reakcję kosztem większej liczby
// requestów/przełączeń warstw; dłuższe uspokajają słabsze urządzenia.
const ORTHO_LAYER_SWAP_FALLBACK_MS = 3000;
const ENHANCEMENT_SETTINGS_SAVE_DEBOUNCE_MS = 350;
