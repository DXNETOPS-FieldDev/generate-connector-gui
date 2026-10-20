"""Shared test fixtures — org data derived from a real multi-hierarchy API response."""

# Subset of a real GET /api/v4/organization response from a multi-hierarchy key.
# Includes multiple root orgs (parentId: 0) and several child hierarchies.
ORGS_MULTI_ROOT = [
    {"id": 1,     "parentId": 0,    "name": "AppNeta Performance Monitoring"},
    {"id": 4160,  "parentId": 0,    "name": "Carousel Industries"},
    {"id": 4166,  "parentId": 0,    "name": "SaskTel"},
    {"id": 4168,  "parentId": 0,    "name": "Columbia Networks Inc."},
    {"id": 4170,  "parentId": 0,    "name": "-[AppNeta]- Customer Care"},
    {"id": 4207,  "parentId": 0,    "name": "Closter BOE"},
    {"id": 4211,  "parentId": 4168, "name": "Columbia Basin Broadband Corp"},
    {"id": 4212,  "parentId": 4168, "name": "Selkirk College"},
    {"id": 4213,  "parentId": 4168, "name": "Coast Capital Savings"},
    {"id": 4222,  "parentId": 4170, "name": "Feature Testing"},
    {"id": 4275,  "parentId": 4160, "name": "Corporate"},
    {"id": 6230,  "parentId": 4166, "name": "SaskTel ICT PS"},
    {"id": 6298,  "parentId": 4170, "name": "SeanHall Org"},
    {"id": 6324,  "parentId": 4160, "name": "Marubeni Trial"},
    {"id": 13581, "parentId": 4160, "name": "Customer Realm"},
]

# Single org-level key: one org, no children.
ORGS_SINGLE = [
    {"id": 18223, "parentId": 0, "name": "TAM - Example Account"},
]

# Org-admin key: one root (Carousel) plus its three direct children.
ORGS_ORG_ADMIN = [
    {"id": 4160,  "parentId": 0,    "name": "Carousel Industries"},
    {"id": 4275,  "parentId": 4160, "name": "Corporate"},
    {"id": 6324,  "parentId": 4160, "name": "Marubeni Trial"},
    {"id": 13581, "parentId": 4160, "name": "Customer Realm"},
]

# Sample monitoring points.
MONITORING_POINTS = [
    {"id": 100, "name": "ACME-MP-MesaFlats",    "type": "m50 microAppliance"},
    {"id": 101, "name": "ACME-MP-CanyonRoad",   "type": "m50 microAppliance"},
    {"id": 102, "name": "ACME-MP-PaintedDesert", "type": "c50 Container"},
    {"id": 103, "name": "ACME-MP-Windows01",    "type": "Windows PathView Agent"},
    {"id": 104, "name": "ACME-MP-Mac01",        "type": "macOS PathView Agent"},
]

# Sample monitoring policies.
POLICIES = [
    {"id": 200, "name": "Southwest Desert"},
    {"id": 201, "name": "Canyon Operations"},
    {"id": 202, "name": "Desert Labs"},
]
