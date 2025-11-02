#    This module provides utility functions for interacting with a SysMLv2-compatible REST API.
#    It includes helpers for querying projects, commits, metadata, elements, and relationships
#    using a persistent requests.Session for efficient HTTP communication.#
#
#    All functions use the global `session` object for HTTP requests.
#
#    Copyright 2025 Tim Weilkiens
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.


import requests

# Global session object
session = requests.Session()

# Utility function to fetch the list of projects from the server
def get_projects(server_url: str) -> list:
    """
    Fetches the list of projects from the server and sorts them alphabetically by name.
    """
    projects_url = f"{server_url}/projects?page%5Bsize%5D=1024"
    print(f"Fetching projects from {projects_url}")
    response = session.get(projects_url)
    if response.status_code != 200:
        raise ValueError(f"Failed to retrieve projects from {projects_url}. Status code: {response.status_code}, details: {response.text}")
    projects = response.json()
    sorted_projects = sorted(projects, key=lambda x: x.get('declaredName', '').lower())
    return sorted_projects

# Utility function to fetch commits for a given project
def get_commits(server_url: str, project_id: str) -> list:
    """
    Fetches the list of commits for a given project.
    """
    if not server_url or not project_id:
        raise ValueError("Both server_url and project_id are required.")

    commits_url = f"{server_url}/projects/{project_id}/commits"
    response = session.get(commits_url)

    if response.status_code != 200:
        raise ValueError(f"Failed to retrieve commits. Status code: {response.status_code}, details: {response.text}")

    commits = response.json()
    if not isinstance(commits, list):
        raise ValueError("Expected a list of commits in the response.")
    # Sort by 'createdAt' if present, otherwise by 'id'
    sorted_commits = sorted(commits, key=lambda x: x.get('createdAt', x.get('id', '')))
    return sorted_commits



def get_metadata_ids_by_name(query_url, metadata_shortnames):
    """
    Fetches the IDs of MetadataDefinition elements based on provided short names.
    """
    query_input = {
        '@type': 'Query',
        'name': 'string',
        'select': ['declaredName', 'declaredShortName','@id', '@type', 'owner'],
        'where': {
            '@type': 'PrimitiveConstraint',
            'inverse': False,
            'operator': '=',
            'property': '@type',
            'value': ['MetadataDefinition']
        }
    }    
    print(f"get_metadata_ids_by_name: query_input: {query_input}")
    try:
        query_response = session.post(query_url, json=query_input)    
        if query_response.status_code == 200:
            query_response_json = query_response.json()
            if isinstance(query_response_json, list):
                print(f"Query response for metadata is a list with {len(query_response_json)} items.")
                print(f"Query response: {query_response_json}")
                id_map = {}
                for shortName in metadata_shortnames:
                    print(f"Searching for metadata with short name: {shortName}")
                    matched_id = next(
                        (item['@id'] for item in query_response_json if item.get('declaredShortName') == shortName),
                        None
                    )
                    id_map[shortName] = matched_id
                print(f"Metadata ID map: {id_map}")
                return id_map
            else:
                print(f"Unexpected response format: not a list. Query Respone: {query_response_json}")
                return {
                    "error": "Unexpected response format",
                    "details": query_response_json
                }
        else:
            print(f"Response code not 200: {query_response}")
            return {
                "error": f"Failed to query metadata. Status code: {query_response.status_code}",
                "details": query_response.text
            }
    except Exception as e:
            print(f"Exception: {e}")
            return {
                "error": str(e)
            }




# Utility function to fetch the IDs of the annotated elements from the metadata usages
def get_metadatausage_annotatedElement_ids(query_url, metadefinition_dict):
    """
    Retrieve annotatedElement IDs for multiple metadataDefinition IDs in a single query.
    """
    
    # Input for querying all MetadataUsage entries
    query_input = {
        '@type': 'Query',
        'where': {
            '@type': 'PrimitiveConstraint',
            'inverse': False,
            'operator': '=',
            'property': '@type',
            'value': ['MetadataUsage']
        }
    }
    print(f"Query Input: {query_input}")
    
    # Send the query
    query_response = session.post(query_url, json=query_input)
    print(f"query response: {query_response}")
    if query_response.status_code != 200:
        raise ValueError(f"Failed to query metadata usages. Status code: {query_response.status_code}, details: {query_response.text}")

    query_response_json = query_response.json()
    if not query_response_json or not isinstance(query_response_json, list):
        return {}

    # Prepare the result dictionary using keys from metadefinition_dict
    results = {metadata_name: [] for metadata_name in metadefinition_dict.keys()}

    # Process each item in the response
    for item in query_response_json:
        metadata = item.get('metadataDefinition')
        metadata_id = metadata.get('@id') if isinstance(metadata, dict) else 'Unknown'
        for key, metadefinition_id in metadefinition_dict.items():
            print(f"Checking if metadata ID {metadata_id} matches metadefinition ID {metadefinition_id} for key: {key}")
            annotated_elements = item.get("annotatedElement", [])
            if annotated_elements:
                if isinstance(annotated_elements, list):
                    for annotated in annotated_elements:
                        print(f"annotated element: {annotated.get('name')}")
            # print(f"metadata: {item}")
            if metadata_id == metadefinition_id:
                print(f"Matched metadataDefinition ID: {metadata_id} for key: {key}")
                # Extract annotatedElement IDs
                annotated_elements = item.get("annotatedElement", [])
                if annotated_elements:
                    if isinstance(annotated_elements, list):
                        for annotated in annotated_elements:
                            annotated_id = annotated.get("@id")
                            if annotated_id:
                                results[key].append(annotated_id)
                    elif isinstance(annotated_elements, dict):
                        annotated_id = annotated_elements.get("@id")
                        if annotated_id:
                            results[key].append(annotated_id)
                else:
                    # Fallback to the main item's @id if annotatedElement is not present
                    results[key].append(item.get("@id"))

    return results

# Utility function to fetch the elements of a given kind from the API
def get_elements_byKind_fromAPI(server_url, project_id, commit_id, kind):

    query_url = f"{server_url}/projects/{project_id}/query-results?commitId={commit_id}"

    query_input = {
        '@type': 'Query',
        'where': {
            '@type': 'PrimitiveConstraint',
            'inverse': False,
            'operator': '=',
            'property': '@type',
            'value': [f"{kind}"]
        }
    }
    try:
        query_response = session.post(query_url, json=query_input)
        if query_response.status_code == 200:
            query_response_json = query_response.json()
            return query_response_json
        else:
            raise ValueError(f"Failed to query kinds. Status code: {query_response.status_code}, details: {query_response.text}")
    except Exception as e:
        print(f"Error: {e}")
        return []

# Utility function to fetch the elements of a given name from the API
def get_elements_byName_fromAPI(server_url, project_id, commit_id, name):
    query_input = {
        '@type': 'Query',
        'where': {
            '@type': 'PrimitiveConstraint',
            'inverse': False,
            'operator': '=',
            'property': 'declaredName',
            'value': [f"{name}"]
        }
    }

    try:
        query_url = f"{server_url}/projects/{project_id}/query-results?commitId={commit_id}"
        query_response = session.post(query_url, json=query_input)
        if query_response.status_code == 200:
            query_response_json = query_response.json()
            additional_elements = []
            for element in query_response_json:
                print(f"Found element: {element.get('declaredName', 'Unknown')} (ID: {element.get('@id', 'Unknown')})")
                elementsOfSameType = get_elements_byKind_fromAPI(server_url, project_id, commit_id, element.get('@type', ''))
                for el in elementsOfSameType:
                    print(f"Processing element of type {el.get('@type', 'Unknown')}: {el.get('declaredName', 'Unknown')} (ID: {el.get('@id', 'Unknown')})")
                    if el.get('@id') != element.get('@id'):
                        for relationshipID in el.get('ownedRelationship', []):
                            relationship = get_element_fromAPI(server_url, project_id, commit_id, relationshipID['@id'])
                            print(f"Found relationship: {relationship.get('@type', 'Unknown')} (ID: {relationship.get('@id', 'Unknown')})")
                            if relationship.get('@type') == "Redefinition":
                                print(f"Found redefinition relationship: {relationshipID}")
                                redefinedFeatureID = relationship.get('redefinedFeature').get('@id')
                                print(f"redefinedFeatureID: {redefinedFeatureID}")
                                redefinedElement = get_element_fromAPI(server_url, project_id, commit_id, redefinedFeatureID)
                                print(f"Redefined element declaredName: {redefinedElement.get('declaredName', 'Unknown')}")

                                # 👉 Check if the redefined element has the declaredName "value"
                                if redefinedElement.get('declaredName') == name:
                                    print("Adding element to query_response_json because redefined elements declaredName is 'value'")
                                    additional_elements.append(el)

            query_response_json.append(additional_elements)
            return query_response_json
        else:
            raise ValueError(f"Failed to query names. Status code: {query_response.status_code}, details: {query_response.text}")
    except Exception as e:
        print(f"Error: {e}")
        return []


# Utility function to fetch the elements for the given IDs
def get_elements_fromAPI(query_url, element_ids):
    elements = []
    for element_id in element_ids:
        try:
            element_json = get_element_fromAPI(query_url, element_id)
            if isinstance(element_json, list):
                elements.extend(element_json)
            else:
                elements.append(element_json)
        except Exception as e:
            print(f"Error processing element id {element_id}: {e}")
            continue  # Continue with the next ID
    return elements

# Utility function to fetch the element for the given ID
def get_element_fromAPI(query_url, element_id):
    try:
        url = query_url + "/elements/" + element_id
        print(f"Query an element: {url}")
        elements_response = session.get(url)
        if elements_response.status_code == 200:
            element = elements_response.json()
            if isinstance(element, list):
                print(f"⚠️ API returned list for element {element_id}, using first item")
                return element[0] if element else None
            print(f"Got element: {element.get('name')}")
            return element
        else:
            print(f"Warning: Failed to retrieve element {element_id}. Status: {elements_response.status_code}")
    except Exception as e:
        print(f"Error processing element id {element_id}: {e}")


def get_owned_elements(server_url, project_id, commit_id, element_id, kind):
    """
    Returns the list of owned elements of a given kind from a specified element.

    :param server_url: URL of the server
    :param project_id: ID of the project
    :param commit_id: ID of the commit
    :param element_id: ID of the parent element
    :param kind: Type filter for owned elements (e.g. 'Class', 'MetadataUsage')
    :return: List of matching owned elements (full data dicts)
    """
    element_data = get_element_fromAPI(server_url, project_id, commit_id, element_id)
    
    if not element_data:
        print(f"Unable to fetch element with id '{element_id}' in commit '{commit_id}' of project '{project_id}'")
        return []

    owned_elements = element_data.get('ownedElement', [])
    matching_elements = []

    for owned_element in owned_elements:
        full_element = get_element_fromAPI(server_url, project_id, commit_id, owned_element['@id'])
        if full_element and full_element.get('@type') == kind:
            matching_elements.append(full_element)

    return matching_elements

def getValueFromOperatorExpressionUnit(query_url, opExp):
    print(f"getValueFromOperatorExpressionUnit called") # with opExp: {opExp}")
    for relationship_id in opExp.get("ownedRelationship"):
        relationship = get_element_fromAPI(query_url, relationship_id["@id"])
        if relationship.get("@type") == 'ParameterMembership' and relationship.get("memberName") == "x":
            memberElement = get_element_fromAPI(query_url, relationship["memberElement"]["@id"])
            featureValue = get_element_fromAPI(query_url, memberElement["ownedRelationship"][0]["@id"])
            return get_element_fromAPI(query_url, featureValue["memberElement"]["@id"])
    return None

def find_element_by_id(aggregated_results, target_id):
    for element in aggregated_results:
        if element['@id'] == target_id:
            return element
    return None  # Return None if not found

