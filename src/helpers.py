import re
from rdflib import Graph, Namespace, Literal, RDF, RDFS, URIRef
from rdflib.namespace import XSD, OWL


def json_to_owl(json_data, namespace: str):
    """
    Converts the given JSON (with 'terms' and 'relations') into an OWL knowledge graph using rdflib.
    The 'additionalInformation' field is split into individual data properties, extracting numeric values and units.

    :param json_data: Dictionary containing 'data' -> { 'terms': [...], 'relations': [...] }
    :return: rdflib.Graph with OWL triples
    """
    g = Graph()

    # Namespaces
    # EX = Namespace("urn:crawlercrane-ontology#")
    EX = Namespace(namespace)
    g.bind("ex", EX)
    g.bind("owl", OWL)

    # Optionally, define a base class for crane components
    CRANE_COMPONENT = EX.CraneComponent
    g.add((CRANE_COMPONENT, RDF.type, OWL.Class))

    # Utility: to store term URI references for easy linking in relations
    term_uris = {}

    # -------------------------------------------------------------------
    # 1) Process Terms (as Individuals of ex:CraneComponent)
    # -------------------------------------------------------------------

    terms_data = json_data.get("data", {}).get("terms", [])

    for term in terms_data:
        term_id = term.get("id")
        term_name = term.get("name", "")
        description = term.get("description", "")
        additional_info = term.get("additionalInformation", "")

        # Create a URI for the term (replace spaces or special chars if needed)
        term_uri = URIRef(EX[term_id.replace(" ", "_")])
        term_uris[term_id] = term_uri

        # Declare term as an individual of ex:CraneComponent
        g.add((term_uri, RDF.type, CRANE_COMPONENT))

        # Add basic metadata
        if term_name:
            g.add((term_uri, RDFS.label, Literal(term_name, datatype=XSD.string)))
        if description:
            g.add((term_uri, RDFS.comment, Literal(description, datatype=XSD.string)))

        # -------------------------------------------------------------------
        # Split and parse additionalInformation:
        # Example string: "maxFlowRate: 266 L/min, maintenanceIntervalCheck: 1000 working hours"
        # -------------------------------------------------------------------
        if additional_info:
            # Split by comma to get each key-value pair
            pairs = [pair.strip() for pair in additional_info.split(",")]
            # Each pair might look like "maxFlowRate: 266 L/min"
            for pair in pairs:
                if ":" not in pair:
                    continue  # skip malformed data
                key, value = pair.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Attempt to extract numeric portion and unit from value
                # e.g., "266 L/min" => number=266, unit="L/min"
                # or "1000 working hours" => number=1000, unit="working hours"

                # A simple approach using regex:
                #   group 1: numeric part (float or int)
                #   group 2: everything else for the unit
                match = re.match(r"^([\d\.]+)\s*(.*)$", value)
                if match:
                    numeric_str = match.group(1)  # "266"
                    unit_str = match.group(2)  # "L/min"
                    # Convert numeric portion to float or int
                    try:
                        if "." in numeric_str:
                            numeric_val = float(numeric_str)
                        else:
                            numeric_val = int(numeric_str)
                    except ValueError:
                        # fallback if numeric_str isn't actually numeric
                        numeric_val = numeric_str
                        unit_str = value  # treat entire string as the unit

                    # Create a data property for the numeric value
                    # ex:HydraulicPumps ex:maxFlowRate "266"^^xsd:float .
                    prop_uri = URIRef(EX[key])
                    g.add((term_uri, prop_uri, Literal(numeric_val, datatype=XSD.float)))

                    # Optionally store the unit as a separate triple
                    # e.g., ex:HydraulicPumps ex:maxFlowRateUnit "L/min"^^xsd:string .
                    if unit_str:
                        prop_unit_uri = URIRef(EX[key + "Unit"])
                        g.add((term_uri, prop_unit_uri, Literal(unit_str, datatype=XSD.string)))
                else:
                    # If we can't parse it as a numeric + unit, store the raw string
                    prop_uri = URIRef(EX[key])
                    g.add((term_uri, prop_uri, Literal(value, datatype=XSD.string)))

    # -------------------------------------------------------------------
    # 2) Process Relations
    # -------------------------------------------------------------------

    relations_data = json_data.get("data", {}).get("relations", [])

    for rel in relations_data:
        rel_name = rel.get("name")
        source_id = rel.get("source")
        target_id = rel.get("target")
        description = rel.get("description", "")

        # Create or get URIs for source and target (fallback if not in terms)
        source_uri = term_uris.get(source_id, URIRef(EX[source_id.replace(" ", "_")]))
        target_uri = term_uris.get(target_id, URIRef(EX[target_id.replace(" ", "_")]))

        # Create an object property for the relationship
        # e.g., ex:ComponentOf, ex:DependsOn, etc.
        rel_uri = URIRef(EX[rel_name])

        # Add triple: source rel_name target
        g.add((source_uri, rel_uri, target_uri))

        if description:
            g.add((rel_uri, RDFS.comment, Literal(description, datatype=XSD.string)))

    return g


def parse_rdf_constraints(output_file):
    """
    Parse the RDF input and return a dictionary with component -> constraint values,
    retaining both numeric values and their units (if present).

    For example:
    constraints["urn:crawlercrane-ontology#Engine"]["maxEngineRpmAtFullLoadSpeed"] = {
        "value": 2000.0,
        "unit": "rpm"
    }
    """
    g = Graph()

    g.parse(output_file, format="turtle")

    # This dictionary will map each component URI to a sub-dict of constraints:
    # e.g. constraints[component_uri] = {
    #     "maxHeaterOutput": {"value": 5.49, "unit": None},
    #     "maintenanceIntervalCheck": {"value": 1000.0, "unit": "working hours"},
    #     ...
    # }
    constraints = {}

    def ensure_component_property_dict(comp, prop):
        """
        Helper to ensure constraints[comp][prop] is at least an empty dict.
        """
        if comp not in constraints:
            constraints[comp] = {}
        if prop not in constraints[comp]:
            constraints[comp][prop] = {"value": None, "unit": None}

    # Look at all (subject, predicate, object) in the graph
    for s, p, o in g:
        # Convert subject/predicate/object to strings
        s_str = str(s)
        p_str = str(p)
        o_str = str(o)

        # Only focus on subject URIs that look like crane components:
        if not s_str.startswith("urn:crawlercrane-ontology#"):
            continue

        # Interpret the property name (the part after the '#')
        pred_name = p_str.split("#")[-1]  # e.g. "maxEngineRpmAtFullLoadSpeed"

        # If the property name ends with 'Unit', assume it's a unit property:
        if pred_name.endswith("Unit"):
            # e.g. "maxEngineRpmAtFullLoadSpeedUnit" => base name is "maxEngineRpmAtFullLoadSpeed"
            base_property = pred_name.replace("Unit", "")  # "maxEngineRpmAtFullLoadSpeed"
            ensure_component_property_dict(s_str, base_property)
            # Set the 'unit' field to the object string (e.g. "rpm")
            constraints[s_str][base_property]["unit"] = o_str
            continue

        # Otherwise, see if 'o' is numeric (try converting to float)
        numeric_value = None
        try:
            numeric_value = float(o_str)
        except ValueError:
            # Not numeric. Possibly a comment or something else.
            pass

        # If a numeric value is recognized, store it as "value".
        # Still store it under the same property name.
        if numeric_value is not None:
            ensure_component_property_dict(s_str, pred_name)
            constraints[s_str][pred_name]["value"] = numeric_value
        else:
            # If it's not numeric skip.
            pass

    return constraints


def extract_relevant_constraints(component_constraints):
    """
    Return a list of potential (sensor_name, max_value, min_value)
    that we can generate telemetry for.
    For example, if there's a key like 'maxEngineRpmAtFullLoadSpeed' = 2000,
    we'll define sensor_name='engine_rpm', max_value=2000, min_value=0.
    """
    relevant_sensors = []

    # A simple parser that looks for any key that starts with "max" or "min" or ends with "Capacity"
    for k, v in component_constraints.items():
        if not isinstance(v, dict):
            continue
        # The main numeric constraint
        val = v.get("value")

        if k.lower().startswith("max"):
            # e.g. "maxEngineRpmAtFullLoadSpeed" => "engine_rpm"
            sensor_name = k[
                3:
            ].lower()  # strip out 'max', make lower, e.g. "enginerpmatfullloadspeed"
            sensor_name = sensor_name.replace("_", "")
            relevant_sensors.append((k, sensor_name, val, 0.0))  # min=0
        elif k.lower().startswith("min"):
            # e.g. "minCarbodyClearance" => "carbody_clearance"
            sensor_name = k[3:].lower()
            relevant_sensors.append((k, sensor_name, None, val))
        elif "capacity" in k.lower():
            # e.g. "fuelTankCapacity" => "fuel_level"
            sensor_name = k.replace("Capacity", "Level").lower()
            relevant_sensors.append((k, sensor_name, val, 0.0))
    return relevant_sensors
