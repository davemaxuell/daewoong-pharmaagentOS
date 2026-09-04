TAXONOMY_VERSION = "drug-taxonomy-v1.0.0"

CATEGORIES = [
    "Quality Unit / QA Oversight",
    "Documentation / GDP / Batch Records",
    "Data Integrity / Computerized Systems / Audit Trail",
    "Training / Qualification / Personnel Practices",
    "Deviations / Investigations / OOS / OOT / CAPA",
    "Aseptic Processing / Sterility Assurance / Media Fill",
    "Contamination Control / Cleaning / Disinfection",
    "Process Validation / PPQ / Continued Process Verification",
    "Equipment / Qualification / Calibration / Maintenance",
    "Facilities / Utilities / HVAC / Water Systems",
    "Laboratory Controls / Method Validation / Microbiology",
    "Stability / Expiry / Retest / Reserve Samples",
    "Materials / Components / Supplier Qualification / COA Reliability",
    "Packaging / Labeling / Container-Closure",
    "Complaints / Adverse Events / Recall / Market Action",
    "Contract Manufacturing / Contract Laboratory / Outsourced Activities",
    "API Manufacturing / ICH Q7-related CGMP",
    "Drug Establishment Registration / Listing / NDC",
    "Misbranding / Unapproved Drug / Marketing Authorization",
    "Distribution / Warehousing / Supply Chain",
    "Change Management",
    "Other Drug Regulatory / CGMP",
]

DRUG_SUBTYPES = [
    "Finished pharmaceutical",
    "Prescription drug",
    "OTC drug",
    "API",
    "Sterile drug",
    "Non-sterile drug",
    "Compounded/503A/503B-related context",
    "Contract manufacturer",
    "Contract testing laboratory",
    "Registration/listing-focused enforcement",
    "Other/unknown",
]

PROCESS_LENSES = ["preventive", "monitoring", "retrospective"]

INTERPRETATION_LABELS = [
    "source_facts",
    "ai_synthesis",
    "internal_comparison",
    "human_reviewed_assessment",
]


def taxonomy_document(version: str = TAXONOMY_VERSION) -> dict[str, object]:
    return {
        "version": version,
        "scope": "FDA Product: Drugs",
        "categories": CATEGORIES,
        "drug_subtypes": DRUG_SUBTYPES,
        "process_lenses": PROCESS_LENSES,
        "interpretation_labels": INTERPRETATION_LABELS,
    }
