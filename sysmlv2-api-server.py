from flask import Flask, send_from_directory, request, jsonify, Response
import requests
from anytree import NodeMixin, RenderTree
import os
import io
import json
import csv
import traceback
import sysmlv2_api_helpers  # Import the sysmlv2_api_helpers module
from typing import Optional
from functools import wraps

app = Flask(__name__, static_folder='sysmlv2Web')
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True  # Optional: Pretty print JSON
app.config['JSONIFY_MIMETYPE'] = 'application/json'

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

# Serve static files (including images)
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

################################################################################################################
#
# Decorator to handle errors in routes
#
def handle_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            return jsonify({"error": f"HTTP error: {str(e)}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return wrapper

################################################################################################################
#
# API Endpoints
#

#
# Retrieve List of Projects on a given Server
#
@app.route('/api/projects', methods=['POST'])
@handle_errors
def api_projects():
    input_data = request.json
    print(f"/api/projects called with data: {input_data}")
    server_url = input_data['server_url']

    # Call the utility function
    projects = sysmlv2_api_helpers.get_projects(server_url)
    print(f"{len(projects)} projects found.")
    return jsonify(projects)

#
# Retrieve List of Commits for a given ProjectID
#
@app.route('/api/commits', methods=['POST'])
@handle_errors
def api_commits():
    input_data = request.json
    print(f"/api/commits called with data: {input_data}")

    # Extract input values
    server_url = input_data.get('server_url')
    project_id = input_data.get('project_id', "").split(' ')[0]  # Safely split and handle edge cases

    # Fetch commits using the utility function
    commits = sysmlv2_api_helpers.get_commits(server_url, project_id)
    return jsonify(commits)

#
# Get all features with given metadata short name and owned attribute usage name; returns feature incl. values
#
@app.route('/api/get-domain-features', methods=['POST'])
@handle_errors
def getDomainFeatures():
    input_data = request.json
    print(f"/api/get-domain-features called with data: {input_data}")

    # Required inputs
    server_url = input_data.get('server_url')
    project_id = input_data.get('project_id')
    commit_id = input_data.get('commit_id')
    domain_name = input_data.get('domain_name', None)
    attribute_name = input_data.get('attribute_name', None)

    if not server_url or not project_id or not commit_id:
        raise ValueError("Server_url, project_id, and commit_id are required.")
    metadata_names = [domain_name]
    query_url = f"{server_url}/projects/{project_id}/query-results?commitId={commit_id}"
    domainDefinitions = sysmlv2_api_helpers.get_metadata_ids_by_name(query_url, metadata_names)
    domainAnnotatedElementsIDs = sysmlv2_api_helpers.get_metadatausage_annotatedElement_ids(query_url, domainDefinitions)
    print(f"domainAnnotatedElementsIDs: {domainAnnotatedElementsIDs}")
    query_url = f"{server_url}/projects/{project_id}/commits/{commit_id}"
    domainElements = sysmlv2_api_helpers.get_elements_fromAPI(query_url, domainAnnotatedElementsIDs.get(domain_name, []))
    # print(f"domainElements: {domainElements}")
    print("Extract attributes values for each element")
    owned_feature_ids = []
    for element in domainElements:
        print(f"Checking: {element.get('name')}")
        for attr in element.get("ownedFeature", []):
            # Each attr can be a dict with "@id" or a plain string
            if isinstance(attr, dict) and "@id" in attr:
                owned_feature_ids.append(attr["@id"])
            elif isinstance(attr, str):
                owned_feature_ids.append(attr)
    print(f"owned_feature_ids: {owned_feature_ids}")

    # Load features
    features = sysmlv2_api_helpers.get_elements_fromAPI(query_url, owned_feature_ids)

    return outputAttributesToCSV(server_url, project_id, commit_id, features)

#
# Returns the value for a given feature
#
@app.route('/api/query-feature-value', methods=['POST'])
@handle_errors
def queryFeatureValue():
    input_data = request.json
    print(f"/api/query-feature-value called with data: {input_data}")

    # Required inputs
    server_url = input_data.get('server_url')
    project_id = input_data.get('project_id')
    commit_id = input_data.get('commit_id')
    element_id = input_data.get('element_id')

    query_url = f"{server_url}/projects/{project_id}/commits/{commit_id}"
    featureValue = sysmlv2_api_helpers.get_element_fromAPI(query_url, element_id)
    if featureValue.get("@type").startswith("Literal"):
        value = featureValue.get("value", "")
    elif featureValue.get("@type") == "OperatorExpression":
        value = sysmlv2_api_helpers.getValueFromOperatorExpressionUnit(query_url, featureValue)
    owner = sysmlv2_api_helpers.get_element_fromAPI(query_url, featureValue.get("owner").get("@id"))
    print(f"featureValue: {owner.get('name', 'Unknown Owner')}={value}")
    return f"{owner.get('name', 'Unknown Owner')}={value}"

#
# Sets the value for a given feature
#
@app.route('/api/write-feature-value', methods=['POST'])
@handle_errors
def writeFeatureValue():
    input_data = request.json
    print(f"/api/write-feature-value called with data: {input_data}")

    # Required inputs
    server_url = input_data.get('server_url')
    project_id = input_data.get('project_id')
    commit_id = input_data.get('commit_id')
    element_id = input_data.get('element_id')
    value = input_data.get('value')

    query_url = f"{server_url}/projects/{project_id}/commits" 
    element = sysmlv2_api_helpers.get_element_fromAPI(query_url + "/" + commit_id, element_id)

    commit_structure = {
        "@type": "Commit",
        "change": [
            {
                "@type": "DataVersion",
                "payload": {
                    "@type": f"{element.get('@type')}",
                    "value": f"{value}",
                    "identifier": f"{element_id}"
                },
                "identity": {
                    "@id": f"{element_id}"
                }
            }
        ],
        "previousCommit": {
            "@id": f"{commit_id}"
        }
    }

    print(f"commit_structure: {commit_structure}")
    commit_post_response = requests.post(query_url, 
                                    headers={"Content-Type": "application/json"}, 
                                    data=json.dumps(commit_structure))
    new_commit_id = ""
    if commit_post_response.status_code == 200:
        commit_response_json = commit_post_response.json()
        new_commit_id  = commit_response_json['@id']
    else:
        print(f"Problem in creating a new commit in project {project_id} - Response {commit_post_response}")
    return f"{new_commit_id}"


################################################################################################################
#
# Helpers
#
def outputAttributesToCSV(server_url, project_id, commit_id, elements):
    try:
        fields = ["@id", "type", "name", "value", "value_id", "owner"]
        csv_elements = []
        for item in elements:
            item = ensure_dict(item)
            if not item:
                print("❌ Skipping invalid item (not a dict):", item)
                continue            
            print(f"Processing item: {item.get('@type')} - {item.get('@id', 'Unknown ID')}")
            if item.get('@type') != 'AttributeUsage':
                continue

            owner = {}
            if isinstance(item.get("owner"), dict):
                query_url = f"{server_url}/projects/{project_id}/commits/{commit_id}"  
                try:
                    owner = sysmlv2_api_helpers.get_element_fromAPI(query_url, item["owner"].get("@id", ""))
                    print(f"Owner found: {owner.get('declaredName', 'Unknown')}")
                except Exception as e:
                    print(f"Warning: failed to fetch owner for {item.get('@id')}: {e}")

            featureValue = getFeatureValueFromFeature(server_url, project_id, commit_id, item.get("@id")) or {}            
            csv_elements.append({
                "@id": item.get("@id", ""),
                "type": item.get("@type", ""),
                "name": item.get("name", ""),
                "value": featureValue.get("value", ""),
                "value_id": featureValue.get("value_id", ""),
                "owner": owner.get("declaredName", "")
            })

        # Create an in-memory file for the CSV content
        csv_output = io.StringIO()

        writer = csv.DictWriter(csv_output, fieldnames=fields)
        writer.writerows(csv_elements)

        csv_content = csv_output.getvalue()
        csv_output.close()
        print(f"CSV content: {csv_content[:200]}")  # Print first 200 chars

    except Exception as e:
        print(f"⚠️ Exception in outputAttributesToCSV: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to generate csv"}), 500


    return csv_content


def ensure_dict(obj):
    """
    Recursively unwrap nested lists until a dictionary is found, or return None.

    This utility function traverses through nested lists by repeatedly unwrapping
    the first element of each list until a non-list object is encountered. If the
    final unwrapped object is a dictionary, it is returned. Otherwise, the function
    returns `None`.

    The function prints diagnostic messages at each step to indicate the unwrapping
    depth and whether the operation succeeded or failed.

    Parameters
    ----------
    obj : any
        The input object, which may be a dictionary, list, or other data type.

    Returns
    -------
    dict or None
        - The first dictionary found after unwrapping nested lists, or
        - `None` if the unwrapped object is not a dictionary or an empty list is encountered.

    Examples
    --------
    >>> ensure_dict({"a": 1})
    {'a': 1}

    >>> ensure_dict([[{"a": 1}]])
    {'a': 1}

    >>> ensure_dict([])
    None

    >>> ensure_dict([["not a dict"]])
    None

    Notes
    -----
    - This function assumes that if `obj` is a list, the first element is the relevant one
      to unwrap further.
    - Debugging messages are printed to the console using Unicode icons to visualize
      progress and failure.
    """
    depth = 0
    while isinstance(obj, list):
        print(f"⚠️ Unwrapping list at depth {depth}: {obj}")
        if not obj:
            return None
        obj = obj[0]
        depth += 1
    if isinstance(obj, dict):
        return obj
    print(f"❌ Failed to unwrap into dict: {obj}")
    return None


def getFeatureValueFromFeature(server_url, project_id, commit_id, feature_id):
    try:
        print(f"getFeatureValueFromFeature called with feature_id: {feature_id}")
        query_url = f"{server_url}/projects/{project_id}/commits/{commit_id}"  
        feature = ensure_dict(sysmlv2_api_helpers.get_element_fromAPI(query_url, feature_id))
        if not feature:
            print("❌ Feature is not a valid dictionary after unwrapping")
            return None

        owned_rel = feature.get("ownedRelationship", [])
        for relationship_id in owned_rel:
            # print(f"Processing relationship: {relationship_id}")
            relationship_id = ensure_dict(relationship_id)
            if not relationship_id:
                print("❌ Invalid relationship_id, cannot get '@id'")
                continue

            rel_id = relationship_id.get("@id")

            if not rel_id:
                continue

            # print(f"Processing relationship ID: {rel_id}")
            relationship = ensure_dict(sysmlv2_api_helpers.get_element_fromAPI(query_url, rel_id))
            if not relationship:
                print("❌ Invalid relationship structure after unwrapping")
                continue

            rel_type = relationship.get("@type")
            # print(f"Relationship type: {rel_type}")

            if rel_type == "FeatureValue":
                related_elements = relationship.get("ownedRelatedElement", [])
                if not related_elements:
                    # print("No ownedRelatedElement in FeatureValue")
                    continue

                # Safely unwrap first related element
                first_related = ensure_dict(related_elements[0])
                if not first_related:
                    print("❌ Failed to unwrap first related element")
                    continue

                related_id = first_related.get("@id")
                if not related_id:
                    print("❌ No @id in related element")
                    continue

                featureValue = ensure_dict(sysmlv2_api_helpers.get_element_fromAPI(query_url, related_id))
                if not featureValue:
                    print("❌ Invalid featureValue structure after unwrapping")
                    continue

                print(f"Feature Value: {featureValue.get('value')}")
                print(f"Feature Type: {featureValue.get('@type')}")
                print(f"Feature ID: {featureValue.get('@id')}")

                fv_type = featureValue.get("@type")
                if not fv_type:
                    continue

                if fv_type.startswith("Literal"):
                    return {
                        "value_id": featureValue.get('@id'),
                        "value": featureValue.get('value')
                    }

                elif fv_type == "OperatorExpression":
                    value = sysmlv2_api_helpers.getValueFromOperatorExpressionUnit(query_url, featureValue)
                    return {
                        "value_id": value.get("@id"),
                        "value": value.get("value")    
                    }

            else:
                print(f"Skipping relationship of type: {rel_type}")

    except Exception as e:
        print(f"⚠️ Exception in getFeatureValueFromFeature: {e}")
        traceback.print_exc()
        return None

    return None


if __name__ == '__main__':
    app.run(debug=True)
