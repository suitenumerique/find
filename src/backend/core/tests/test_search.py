"""Tests for the search module"""

# pylint: disable=too-many-lines

import pytest
from opensearchpy import Q

from core import enums, factories
from core.services.opensearch import opensearch_client
from core.services.search import (
    SortSpec,
    get_filter,
    get_full_text_query,
    get_query,
    get_sort,
)
from core.utils import prepare_index

pytestmark = pytest.mark.django_db


# Test constants for predictable test data
TEST_USER_SUB = "test-user-sub-123"
TEST_OTHER_USER_SUB = "other-user-sub-456"
TEST_GROUP = "test-group-alpha"
TEST_OTHER_GROUP = "test-group-beta"


def get_search_test_documents():
    """
    Return a list of predictable test documents for search testing.

    Creates diverse documents covering different access patterns:
    - Public documents (visible to anyone with visited list)
    - Authenticated documents (visible to any authenticated user)
    - Restricted documents with specific user access
    - Restricted documents with specific group access
    - Documents with varied tags and paths for filter testing

    Returns:
        List[dict]: 6+ test documents with explicit, predictable values
    """
    return [
        # 1. Public document - anyone with visited can see
        factories.DocumentSchemaFactory.build(
            id="doc-public-1",
            reach=enums.ReachEnum.PUBLIC,
            users=[],
            groups=[],
            tags=["tag-alpha", "tag-beta"],
            path="/public/folder",
            title="Public Document Alpha",
            content="This is a public document visible to everyone",
        ),
        # 2. Public document with different tags
        factories.DocumentSchemaFactory.build(
            id="doc-public-2",
            reach=enums.ReachEnum.PUBLIC,
            users=[],
            groups=[],
            tags=["tag-gamma"],
            path="/public/other",
            title="Public Document Beta",
            content="Another public document with different tags",
        ),
        # 3. Authenticated document - visible to any authenticated user
        factories.DocumentSchemaFactory.build(
            id="doc-authenticated-1",
            reach=enums.ReachEnum.AUTHENTICATED,
            users=[],
            groups=[],
            tags=["tag-alpha"],
            path="/authenticated/folder",
            title="Authenticated Document",
            content="This document is visible to authenticated users only",
        ),
        # 4. Restricted document - specific user access
        factories.DocumentSchemaFactory.build(
            id="doc-restricted-user-1",
            reach=enums.ReachEnum.RESTRICTED,
            users=[TEST_USER_SUB],
            groups=[],
            tags=["tag-beta", "tag-delta"],
            path="/restricted/user-folder",
            title="Restricted User Document",
            content="This document is restricted to a specific user",
        ),
        # 5. Restricted document - different user access
        factories.DocumentSchemaFactory.build(
            id="doc-restricted-user-2",
            reach=enums.ReachEnum.RESTRICTED,
            users=[TEST_OTHER_USER_SUB],
            groups=[],
            tags=["tag-gamma"],
            path="/restricted/other-user",
            title="Other User Restricted Document",
            content="This document is restricted to a different user",
        ),
        # 6. Restricted document - group access
        factories.DocumentSchemaFactory.build(
            id="doc-restricted-group-1",
            reach=enums.ReachEnum.RESTRICTED,
            users=[],
            groups=[TEST_GROUP],
            tags=["tag-alpha", "tag-gamma"],
            path="/restricted/group-folder",
            title="Restricted Group Document",
            content="This document is restricted to a specific group",
        ),
        # 7. Restricted document - different group access
        factories.DocumentSchemaFactory.build(
            id="doc-restricted-group-2",
            reach=enums.ReachEnum.RESTRICTED,
            users=[],
            groups=[TEST_OTHER_GROUP],
            tags=["tag-beta"],
            path="/restricted/other-group",
            title="Other Group Restricted Document",
            content="This document is restricted to a different group",
        ),
    ]


@pytest.fixture
def search_index_with_documents(settings):  # pylint: disable=unused-argument
    """
    Create a service and index with diverse test documents.

    This fixture:
    - Creates a test service
    - Generates diverse test documents with varied reach, users, groups, tags, and paths
    - Indexes them in OpenSearch
    - Returns the service and documents for test use

    Args:
        settings: Django settings fixture (ensures Django is configured)

    Yields:
        Tuple[Service, List[dict]]: (service instance, list of indexed documents)
    """
    service = factories.ServiceFactory()
    documents = get_search_test_documents()
    prepare_index(service.index_name, documents)
    yield service, documents


def assert_query_equivalent(expected_dict: dict, q_object) -> None:
    """
    Assert that a Q-object's to_dict() output matches the expected dict structure.

    Performs a deep comparison of the Q-object's dictionary representation against
    the expected dictionary. On mismatch, raises AssertionError with a clear diff
    showing exactly what differs.

    Args:
        expected_dict: The expected query as a raw dictionary
        q_object: An opensearch-py Q object

    Raises:
        AssertionError: If structures don't match, with clear diff showing differences

    Example:
        >>> q = Q('match', title='test')
        >>> assert_query_equivalent({'match': {'title': 'test'}}, q)
        >>> # Raises AssertionError if q.to_dict() doesn't match
    """
    actual_dict = q_object.to_dict()

    if actual_dict == expected_dict:
        return

    # Build a clear diff message
    diff_msg = _build_diff_message(expected_dict, actual_dict)
    raise AssertionError(
        f"Query structures don't match.\n"
        f"Expected:\n{expected_dict}\n\n"
        f"Actual:\n{actual_dict}\n\n"
        f"Diff:\n{diff_msg}"
    )


def _build_diff_message(expected: dict, actual: dict, path: str = "root") -> str:
    """
    Build a human-readable diff message showing differences between two dicts.

    Args:
        expected: Expected dictionary
        actual: Actual dictionary
        path: Current path in the nested structure (for error messages)

    Returns:
        String describing the differences
    """
    diffs = []

    # Check for keys in expected but not in actual
    for key, value in expected.items():
        if key not in actual:
            diffs.append(f"  Missing key at {path}.{key}")
        elif value != actual[key]:
            if isinstance(value, dict) and isinstance(actual[key], dict):
                diffs.append(_build_diff_message(value, actual[key], f"{path}.{key}"))
            else:
                diffs.append(
                    f"  Value mismatch at {path}.{key}:\n"
                    f"    Expected: {value}\n"
                    f"    Actual:   {actual[key]}"
                )

    # Check for keys in actual but not in expected
    for key, value in actual.items():
        if key not in expected:
            diffs.append(f"  Extra key at {path}.{key}: {value}")

    return "\n".join(diffs) if diffs else "No differences found"


def test_search_infrastructure_ready():
    """Verify test infrastructure is properly configured."""
    assert True


def test_assert_query_equivalent_works():
    """Verify the assert_query_equivalent utility function works correctly."""
    # Test 1: Matching queries should pass silently
    q = Q("match", title="test")
    expected = {"match": {"title": "test"}}
    assert_query_equivalent(expected, q)  # Should not raise

    # Test 2: Mismatching queries should raise AssertionError with clear message
    q_mismatch = Q("term", status="active")
    expected_mismatch = {"match": {"title": "test"}}

    with pytest.raises(AssertionError) as exc_info:
        assert_query_equivalent(expected_mismatch, q_mismatch)

    error_msg = str(exc_info.value)
    assert "Query structures don't match" in error_msg
    assert "Expected:" in error_msg
    assert "Actual:" in error_msg
    assert "Diff:" in error_msg

    # Test 3: Nested structures should work
    q_nested = Q("bool", should=[Q("match", title="test"), Q("term", status="active")])
    expected_nested = q_nested.to_dict()
    assert_query_equivalent(expected_nested, q_nested)  # Should not raise


def test_get_search_test_documents_diversity():
    """Verify get_search_test_documents creates diverse test documents."""
    documents = get_search_test_documents()

    assert len(documents) >= 6, "Should have at least 6 test documents"

    doc_ids = [doc["id"] for doc in documents]
    assert len(set(doc_ids)) == len(doc_ids), "All document IDs should be unique"

    reaches = [doc["reach"] for doc in documents]
    assert enums.ReachEnum.PUBLIC in reaches, "Should have public documents"
    assert enums.ReachEnum.AUTHENTICATED in reaches, (
        "Should have authenticated documents"
    )
    assert enums.ReachEnum.RESTRICTED in reaches, "Should have restricted documents"

    user_docs = [doc for doc in documents if doc["users"]]
    assert len(user_docs) >= 2, "Should have documents with user restrictions"

    group_docs = [doc for doc in documents if doc["groups"]]
    assert len(group_docs) >= 2, "Should have documents with group restrictions"

    tagged_docs = [doc for doc in documents if doc["tags"]]
    assert len(tagged_docs) >= 4, "Should have documents with tags"

    path_docs = [doc for doc in documents if doc["path"]]
    assert len(path_docs) == len(documents), "All documents should have paths"


def test_search_index_with_documents_fixture(
    search_index_with_documents,  # pylint: disable=redefined-outer-name
):
    """Verify the search_index_with_documents fixture creates and indexes documents."""
    service, documents = search_index_with_documents

    assert service is not None, "Fixture should return a service"
    assert documents is not None, "Fixture should return documents"
    assert len(documents) >= 6, "Fixture should create at least 6 documents"

    client = opensearch_client()
    for doc in documents:
        result = client.get(index=service.index_name, id=doc["id"])
        assert result["found"], f"Document {doc['id']} should be indexed"
        source = result["_source"]
        assert source["id"] == doc["id"], "Document ID should match"
        assert source["reach"] == doc["reach"], "Document reach should match"
        assert source["users"] == doc["users"], "Document users should match"
        assert source["groups"] == doc["groups"], "Document groups should match"
        assert source["tags"] == doc["tags"], "Document tags should match"


# =============================================================================
# get_filter() unit tests - SECURITY CRITICAL ACCESS CONTROL
# =============================================================================


class TestGetFilterBaseStructure:
    """Tests for get_filter() base structure - always present filters."""

    def test_get_filter_base_structure_always_has_is_active_and_access_control(self):
        """Test get_filter always returns is_active and access control filters."""
        result = get_filter(
            reach=None,
            visited=["doc1", "doc2"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Base structure: at least 2 filters (is_active + access control)
        assert len(result) >= 2, "Should have at least is_active and access control"

        # First filter is always is_active
        assert result[0].to_dict() == {"term": {"is_active": True}}, (
            "First filter must be is_active"
        )

        # Second filter is the access control bool
        ac = result[1].to_dict()
        assert "bool" in ac, "Second filter must be access control bool"
        assert "should" in ac["bool"], "Access control must have should clause"
        assert ac["bool"].get("minimum_should_match") == 1, (
            "Must require at least one match"
        )

    def test_get_filter_is_active_always_first(self):
        """Test is_active filter is always the first filter regardless of params."""
        # Test with all optional params
        result = get_filter(
            reach=enums.ReachEnum.PUBLIC,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag1"],
            path="/some/path",
        )
        assert result[0].to_dict() == {"term": {"is_active": True}}

        # Test with minimal params
        result_minimal = get_filter(
            reach=None,
            visited=[],
            user_sub="",
            groups=[],
            tags=[],
            path=None,
        )
        assert result_minimal[0].to_dict() == {"term": {"is_active": True}}


class TestGetFilterAccessControl:
    """Tests for get_filter() access control - THREE paths for document access."""

    def test_get_filter_access_control_has_three_paths(self):
        """Test access control has exactly 3 paths: visited, user match, group match."""
        result = get_filter(
            reach=None,
            visited=["doc1", "doc2"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP, TEST_OTHER_GROUP],
            tags=[],
            path=None,
        )

        access_control = result[1].to_dict()["bool"]["should"]
        assert len(access_control) == 3, "Access control must have exactly 3 paths"

    def test_get_filter_access_control_path1_visited_non_restricted(self):
        """Test path 1: public/auth docs must be in visited list and not restricted."""
        result = get_filter(
            reach=None,
            visited=["doc-public", "doc-auth"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        access_control = result[1].to_dict()["bool"]["should"]
        path1 = access_control[0]

        # Path 1 is a bool with must_not restricted AND must be in visited
        assert "bool" in path1, "Path 1 must be a bool query"
        assert "must_not" in path1["bool"], "Path 1 must have must_not clause"
        assert "must" in path1["bool"], "Path 1 must have must clause"

        # must_not: reach != restricted (Q wraps in list)
        must_not = path1["bool"]["must_not"][0]
        assert must_not == {"term": {enums.REACH: enums.ReachEnum.RESTRICTED}}

        # must: _id in visited (sorted) (Q wraps in list)
        must = path1["bool"]["must"][0]
        assert must == {"terms": {"_id": ["doc-auth", "doc-public"]}}  # sorted!

    def test_get_filter_access_control_path2_user_match(self):
        """Test path 2: restricted documents accessible via user match."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        access_control = result[1].to_dict()["bool"]["should"]
        path2 = access_control[1]

        assert path2 == {"term": {enums.USERS: TEST_USER_SUB}}

    def test_get_filter_access_control_path3_group_match(self):
        """Test path 3: restricted documents accessible via group match."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP, TEST_OTHER_GROUP],
            tags=[],
            path=None,
        )

        access_control = result[1].to_dict()["bool"]["should"]
        path3 = access_control[2]

        # Path 3: any group must match
        assert path3 == {"terms": {enums.GROUPS: [TEST_GROUP, TEST_OTHER_GROUP]}}

    def test_get_filter_visited_documents_sorted(self):
        """Test visited document IDs are sorted in the filter for consistent queries."""
        result = get_filter(
            reach=None,
            visited=["zebra", "apple", "mango"],  # unsorted
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        path1 = result[1].to_dict()["bool"]["should"][0]
        visited_in_filter = path1["bool"]["must"][0]["terms"]["_id"]

        assert visited_in_filter == ["apple", "mango", "zebra"], (
            "Visited IDs must be sorted"
        )


class TestGetFilterReachOption:
    """Tests for get_filter() optional reach filter."""

    def test_get_filter_with_reach_public(self):
        """Test reach filter is appended when reach is public."""
        result = get_filter(
            reach=enums.ReachEnum.PUBLIC,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Should have 3 filters: is_active, access_control, reach
        assert len(result) == 3
        assert result[2].to_dict() == {"term": {enums.REACH: enums.ReachEnum.PUBLIC}}

    def test_get_filter_with_reach_authenticated(self):
        """Test reach filter is appended when reach is authenticated."""
        result = get_filter(
            reach=enums.ReachEnum.AUTHENTICATED,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        assert len(result) == 3
        assert result[2].to_dict() == {
            "term": {enums.REACH: enums.ReachEnum.AUTHENTICATED}
        }

    def test_get_filter_with_reach_restricted(self):
        """Test reach filter is appended when reach is restricted."""
        result = get_filter(
            reach=enums.ReachEnum.RESTRICTED,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        assert len(result) == 3
        assert result[2].to_dict() == {
            "term": {enums.REACH: enums.ReachEnum.RESTRICTED}
        }

    def test_get_filter_reach_none_omits_reach_filter(self):
        """Test reach filter is NOT added when reach is None."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Only 2 filters: is_active, access_control
        assert len(result) == 2
        # Verify no reach filter present
        for filter_ in result:
            f = filter_.to_dict()
            if "term" in f and enums.REACH in f.get("term", {}):
                pytest.fail("reach filter should not be present when reach is None")


class TestGetFilterTagsOption:
    """Tests for get_filter() optional tags filter."""

    def test_get_filter_with_single_tag(self):
        """Test tags filter is appended with a single tag."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag-alpha"],
            path=None,
        )

        # Should have 3 filters: is_active, access_control, tags
        assert len(result) == 3
        assert result[2].to_dict() == {"terms": {"tags": ["tag-alpha"]}}

    def test_get_filter_with_multiple_tags(self):
        """Test tags filter is appended with multiple tags (logical OR)."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag-alpha", "tag-beta", "tag-gamma"],
            path=None,
        )

        assert len(result) == 3
        assert result[2].to_dict() == {
            "terms": {"tags": ["tag-alpha", "tag-beta", "tag-gamma"]}
        }

    def test_get_filter_empty_tags_omits_tags_filter(self):
        """Test tags filter is NOT added when tags list is empty."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Only 2 filters: is_active, access_control
        assert len(result) == 2
        # Verify no tags filter present
        for filter_ in result:
            f = filter_.to_dict()
            if "terms" in f and "tags" in f.get("terms", {}):
                pytest.fail("tags filter should not be present when tags is empty")


class TestGetFilterPathOption:
    """Tests for get_filter() optional path prefix filter."""

    def test_get_filter_with_path_prefix(self):
        """Test path prefix filter is appended when path is provided."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path="/public/folder",
        )

        # Should have 3 filters: is_active, access_control, path
        assert len(result) == 3
        assert result[2].to_dict() == {"prefix": {"path": "/public/folder"}}

    def test_get_filter_path_none_omits_path_filter(self):
        """Test path filter is NOT added when path is None."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Only 2 filters: is_active, access_control
        assert len(result) == 2
        # Verify no path filter present
        for filter_ in result:
            if "prefix" in filter_.to_dict():
                pytest.fail("path filter should not be present when path is None")

    def test_get_filter_path_empty_string_omits_path_filter(self):
        """Test path filter is NOT added when path is empty string (falsy)."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path="",
        )

        # Only 2 filters: is_active, access_control
        assert len(result) == 2


class TestGetFilterEdgeCases:
    """Tests for get_filter() edge cases."""

    def test_get_filter_empty_groups_list(self):
        """Test filter works correctly with empty groups list."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[],  # empty groups
            tags=[],
            path=None,
        )

        # Should still have all 3 access control paths
        access_control = result[1].to_dict()["bool"]["should"]
        assert len(access_control) == 3

        # Path 3 should have empty groups list
        path3 = access_control[2]
        assert path3 == {"terms": {enums.GROUPS: []}}

    def test_get_filter_empty_visited_list(self):
        """Test filter works correctly with empty visited list."""
        result = get_filter(
            reach=None,
            visited=[],  # empty visited
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Should still have all 3 access control paths
        access_control = result[1].to_dict()["bool"]["should"]
        assert len(access_control) == 3

        # Path 1 should have empty visited list (Q wraps in list)
        path1 = access_control[0]
        assert path1["bool"]["must"] == [{"terms": {"_id": []}}]

    def test_get_filter_empty_user_sub(self):
        """Test filter works correctly with empty user_sub."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub="",  # empty user_sub
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        )

        # Should still have all 3 access control paths
        access_control = result[1].to_dict()["bool"]["should"]
        assert len(access_control) == 3

        # Path 2 should have empty user_sub
        path2 = access_control[1]
        assert path2 == {"term": {enums.USERS: ""}}


class TestGetFilterCombined:
    """Tests for get_filter() with multiple optional filters combined."""

    def test_get_filter_all_optional_filters_combined(self):
        """Test all optional filters are appended in correct order."""
        result = get_filter(
            reach=enums.ReachEnum.PUBLIC,
            visited=["doc1", "doc2"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag-alpha", "tag-beta"],
            path="/public/folder",
        )

        # Should have 5 filters: is_active, access_control, reach, tags, path
        assert len(result) == 5

        # Verify order
        assert result[0].to_dict() == {"term": {"is_active": True}}
        assert "bool" in result[1].to_dict()  # access control
        assert result[2].to_dict() == {"term": {enums.REACH: enums.ReachEnum.PUBLIC}}
        assert result[3].to_dict() == {"terms": {"tags": ["tag-alpha", "tag-beta"]}}
        assert result[4].to_dict() == {"prefix": {"path": "/public/folder"}}

    def test_get_filter_reach_and_tags_no_path(self):
        """Test reach and tags filters without path."""
        result = get_filter(
            reach=enums.ReachEnum.AUTHENTICATED,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag-gamma"],
            path=None,
        )

        # Should have 4 filters: is_active, access_control, reach, tags
        assert len(result) == 4
        assert result[2].to_dict() == {
            "term": {enums.REACH: enums.ReachEnum.AUTHENTICATED}
        }
        assert result[3].to_dict() == {"terms": {"tags": ["tag-gamma"]}}

    def test_get_filter_reach_and_path_no_tags(self):
        """Test reach and path filters without tags."""
        result = get_filter(
            reach=enums.ReachEnum.RESTRICTED,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path="/restricted/folder",
        )

        # Should have 4 filters: is_active, access_control, reach, path
        assert len(result) == 4
        assert result[2].to_dict() == {
            "term": {enums.REACH: enums.ReachEnum.RESTRICTED}
        }
        assert result[3].to_dict() == {"prefix": {"path": "/restricted/folder"}}

    def test_get_filter_tags_and_path_no_reach(self):
        """Test tags and path filters without reach."""
        result = get_filter(
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag-delta"],
            path="/some/path",
        )

        # Should have 4 filters: is_active, access_control, tags, path
        assert len(result) == 4
        assert result[2].to_dict() == {"terms": {"tags": ["tag-delta"]}}
        assert result[3].to_dict() == {"prefix": {"path": "/some/path"}}


# =============================================================================
# Tests for get_full_text_query()
# =============================================================================


def test_get_full_text_query_structure():
    """Test full-text query has correct nested bool structure."""
    filter_ = [Q("term", is_active=True)]
    result = get_full_text_query("test query", filter_).to_dict()

    # Top-level bool
    assert "bool" in result
    assert "must" in result["bool"]
    assert "filter" in result["bool"]

    # Nested bool inside must (Q wraps in list)
    inner_bool = result["bool"]["must"][0]
    assert "bool" in inner_bool
    assert "should" in inner_bool["bool"]
    assert "minimum_should_match" in inner_bool["bool"]
    assert inner_bool["bool"]["minimum_should_match"] == 1


def test_get_full_text_query_multi_match_fields():
    """Test full-text query includes correct fields for standard multi_match."""
    filter_ = []
    result = get_full_text_query("test", filter_).to_dict()

    should = result["bool"]["must"][0]["bool"]["should"]
    assert len(should) == 2, "Should have exactly 2 multi_match queries"

    # First multi_match - standard text fields
    first_multi_match = should[0]["multi_match"]
    assert first_multi_match["query"] == "test"
    assert first_multi_match["fields"] == ["title.*.text^3", "content.*"]


def test_get_full_text_query_trigram_fields():
    """Test full-text query includes correct fields for trigram multi_match."""
    filter_ = []
    result = get_full_text_query("fuzzy search", filter_).to_dict()

    should = result["bool"]["must"][0]["bool"]["should"]
    assert len(should) == 2

    # Second multi_match - trigram fields
    second_multi_match = should[1]["multi_match"]
    assert second_multi_match["query"] == "fuzzy search"
    assert second_multi_match["fields"] == [
        "title.*.text.trigrams^3",
        "content.*.trigrams",
    ]


def test_get_full_text_query_trigram_boost_and_minimum(settings):
    """Test trigram query has correct boost and minimum_should_match from settings."""
    # Explicitly set settings to avoid environment-dependent test failures
    settings.TRIGRAMS_BOOST = 0.25
    settings.TRIGRAMS_MINIMUM_SHOULD_MATCH = "75%"

    filter_ = []
    result = get_full_text_query("test", filter_).to_dict()

    trigram_query = result["bool"]["must"][0]["bool"]["should"][1]["multi_match"]

    # Verify boost matches settings
    assert trigram_query["boost"] == settings.TRIGRAMS_BOOST

    # Verify minimum_should_match matches settings
    assert (
        trigram_query["minimum_should_match"] == settings.TRIGRAMS_MINIMUM_SHOULD_MATCH
    )


def test_get_full_text_query_filter_embedded():
    """Test that filter is properly embedded in the query structure."""
    custom_filter = [
        Q("term", is_active=True),
        Q("terms", tags=["tag1", "tag2"]),
    ]
    result = get_full_text_query("test query", custom_filter).to_dict()

    assert result["bool"]["filter"] == [f.to_dict() for f in custom_filter]


def test_get_full_text_query_empty_filter():
    """Test full-text query works with empty filter."""
    result = get_full_text_query("test", []).to_dict()

    # Empty filter is omitted by Q serialization
    assert result["bool"].get("filter", []) == []
    # Query structure should still be complete
    assert "must" in result["bool"]
    assert "should" in result["bool"]["must"][0]["bool"]


# =============================================================================
# get_sort() Tests
# =============================================================================


class TestGetSort:
    """Tests for the get_sort() function.

    The get_sort() function builds OpenSearch sort clauses for search results.
    It handles two cases:
    - relevance: Uses "_score" as the sort field
    - other fields: Uses the field name directly as the sort field

    ORDER_BY_OPTIONS: relevance, title, created_at, updated_at, size, reach
    """

    def test_get_sort_relevance_desc(self):
        """Test sorting by relevance in descending order.

        Relevance sorting uses the special "_score" field in OpenSearch,
        which represents the relevance score calculated during search.
        Descending order returns most relevant results first (typical use case).
        """
        result = get_sort(enums.RELEVANCE, "desc")
        assert result == SortSpec("_score", "desc")

    def test_get_sort_relevance_asc(self):
        """Test sorting by relevance in ascending order.

        Relevance sorting uses the special "_score" field in OpenSearch.
        Ascending order returns least relevant results first (unusual but valid).
        """
        result = get_sort(enums.RELEVANCE, "asc")
        assert result == SortSpec("_score", "asc")

    def test_get_sort_title_desc(self):
        """Test sorting by title in descending order.

        Title sorting uses the title field directly.
        Descending order returns titles in reverse alphabetical order (Z-A).
        """
        result = get_sort(enums.TITLE, "desc")
        assert result == SortSpec("title", "desc")

    def test_get_sort_title_asc(self):
        """Test sorting by title in ascending order.

        Title sorting uses the title field directly.
        Ascending order returns titles in alphabetical order (A-Z).
        """
        result = get_sort(enums.TITLE, "asc")
        assert result == SortSpec("title", "asc")

    def test_get_sort_created_at_desc(self):
        """Test sorting by created_at in descending order.

        Created_at sorting uses the created_at field directly.
        Descending order returns newest documents first.
        """
        result = get_sort(enums.CREATED_AT, "desc")
        assert result == SortSpec("created_at", "desc")

    def test_get_sort_created_at_asc(self):
        """Test sorting by created_at in ascending order.

        Created_at sorting uses the created_at field directly.
        Ascending order returns oldest documents first.
        """
        result = get_sort(enums.CREATED_AT, "asc")
        assert result == SortSpec("created_at", "asc")

    def test_get_sort_updated_at_desc(self):
        """Test sorting by updated_at in descending order.

        Updated_at sorting uses the updated_at field directly.
        Descending order returns recently modified documents first.
        """
        result = get_sort(enums.UPDATED_AT, "desc")
        assert result == SortSpec("updated_at", "desc")

    def test_get_sort_updated_at_asc(self):
        """Test sorting by updated_at in ascending order.

        Updated_at sorting uses the updated_at field directly.
        Ascending order returns least recently modified documents first.
        """
        result = get_sort(enums.UPDATED_AT, "asc")
        assert result == SortSpec("updated_at", "asc")

    def test_get_sort_size_desc(self):
        """Test sorting by size in descending order.

        Size sorting uses the size field directly.
        Descending order returns largest documents first.
        """
        result = get_sort(enums.SIZE, "desc")
        assert result == SortSpec("size", "desc")

    def test_get_sort_size_asc(self):
        """Test sorting by size in ascending order.

        Size sorting uses the size field directly.
        Ascending order returns smallest documents first.
        """
        result = get_sort(enums.SIZE, "asc")
        assert result == SortSpec("size", "asc")

    def test_get_sort_reach_desc(self):
        """Test sorting by reach in descending order.

        Reach sorting uses the reach field directly.
        This sorts by document visibility level.
        """
        result = get_sort(enums.REACH, "desc")
        assert result == SortSpec("reach", "desc")

    def test_get_sort_reach_asc(self):
        """Test sorting by reach in ascending order.

        Reach sorting uses the reach field directly.
        This sorts by document visibility level.
        """
        result = get_sort(enums.REACH, "asc")
        assert result == SortSpec("reach", "asc")


# =============================================================================
# get_query() Tests
# =============================================================================


class TestGetQuery:
    """Tests for the get_query() function.

    The get_query() function builds the complete OpenSearch query body.
    It handles two cases:
    - q == "*": Returns match_all query with filter
    - q != "*": Returns full-text search query via get_full_text_query()

    Both cases embed the filter from get_filter() into the bool query structure.
    """

    def test_get_query_match_all_returns_bool_structure(self):
        """Test get_query with '*' returns proper bool structure.

        When q="*", the query should be a match_all wrapped in a bool
        with filter clause containing nested bool.
        """
        result = get_query(
            query="*",
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        ).to_dict()

        # Verify top-level bool structure
        assert "bool" in result
        assert "must" in result["bool"]
        assert "filter" in result["bool"]

        # Verify match_all in must clause (Q wraps in list)
        assert result["bool"]["must"] == [{"match_all": {}}]

        # Verify filter is nested in bool structure (Q wraps in list)
        assert "bool" in result["bool"]["filter"][0]
        assert "filter" in result["bool"]["filter"][0]["bool"]

    def test_get_query_full_text_returns_bool_structure(self):
        """Test get_query with search term returns proper bool structure.

        When q!="*", the query should be a full-text search with
        multi_match queries wrapped in a bool.
        """
        result = get_query(
            query="search term",
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        ).to_dict()

        # Verify top-level bool structure
        assert "bool" in result
        assert "must" in result["bool"]
        assert "filter" in result["bool"]

        # Verify must clause contains nested bool with should (Q wraps in list)
        must_clause = result["bool"]["must"][0]
        assert "bool" in must_clause
        assert "should" in must_clause["bool"]

        # Verify should contains multi_match queries
        should_clauses = must_clause["bool"]["should"]
        assert len(should_clauses) == 2
        assert "multi_match" in should_clauses[0]
        assert "multi_match" in should_clauses[1]

        # Verify query term is in the multi_match
        assert should_clauses[0]["multi_match"]["query"] == "search term"

    def test_get_query_match_all_embeds_filter_correctly(self):
        """Test get_query with '*' correctly embeds filter from get_filter().

        The filter list from get_filter() should be embedded inside:
        filter -> [0] -> bool -> filter
        """
        result = get_query(
            query="*",
            reach=None,
            visited=["doc1", "doc2"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        ).to_dict()

        # Get the nested filter list (Q wraps outer filter in list)
        filter_list = result["bool"]["filter"][0]["bool"]["filter"]

        # Should be a list (from get_filter)
        assert isinstance(filter_list, list)

        # Should contain is_active filter
        is_active_filters = [
            f for f in filter_list if "term" in f and "is_active" in f.get("term", {})
        ]
        assert len(is_active_filters) == 1
        assert is_active_filters[0]["term"]["is_active"] is True

        # Should contain access control filter (bool with should)
        access_filters = [
            f for f in filter_list if "bool" in f and "should" in f.get("bool", {})
        ]
        assert len(access_filters) == 1

    def test_get_query_full_text_embeds_filter_correctly(self):
        """Test get_query with search term correctly embeds filter.

        For full-text queries, the filter list is passed directly to
        the top-level bool filter clause (not nested in another bool).
        """
        result = get_query(
            query="test query",
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        ).to_dict()

        # Get the filter - for full-text it's directly a list
        filter_list = result["bool"]["filter"]

        # Should be a list (from get_filter)
        assert isinstance(filter_list, list)

        # Should contain is_active filter
        is_active_filters = [
            f for f in filter_list if "term" in f and "is_active" in f.get("term", {})
        ]
        assert len(is_active_filters) == 1

    def test_get_query_with_reach_filter(self):
        """Test get_query includes reach filter when reach is specified.

        When reach parameter is not None, the filter should include
        a term filter for the reach value.
        """
        result = get_query(
            query="*",
            reach=enums.ReachEnum.PUBLIC,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path=None,
        ).to_dict()

        # Q wraps outer filter in list
        filter_list = result["bool"]["filter"][0]["bool"]["filter"]

        # Should contain reach filter
        reach_filters = [
            f for f in filter_list if "term" in f and enums.REACH in f.get("term", {})
        ]
        assert len(reach_filters) == 1
        assert reach_filters[0]["term"][enums.REACH] == enums.ReachEnum.PUBLIC

    def test_get_query_with_tags_filter(self):
        """Test get_query includes tags filter when tags are specified.

        When tags parameter is not empty, the filter should include
        a terms filter for the tags values.
        """
        result = get_query(
            query="search",
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=["tag-alpha", "tag-beta"],
            path=None,
        ).to_dict()

        filter_list = result["bool"]["filter"]

        # Should contain tags filter
        tags_filters = [
            f for f in filter_list if "terms" in f and "tags" in f.get("terms", {})
        ]
        assert len(tags_filters) == 1
        assert set(tags_filters[0]["terms"]["tags"]) == {"tag-alpha", "tag-beta"}

    def test_get_query_with_path_filter(self):
        """Test get_query includes path prefix filter when path is specified.

        When path parameter is not None, the filter should include
        a prefix filter for the path value.
        """
        result = get_query(
            query="*",
            reach=None,
            visited=["doc1"],
            user_sub=TEST_USER_SUB,
            groups=[TEST_GROUP],
            tags=[],
            path="/restricted/folder",
        ).to_dict()

        # Q wraps outer filter in list
        filter_list = result["bool"]["filter"][0]["bool"]["filter"]

        # Should contain path prefix filter
        path_filters = [
            f for f in filter_list if "prefix" in f and "path" in f.get("prefix", {})
        ]
        assert len(path_filters) == 1
        assert path_filters[0]["prefix"]["path"] == "/restricted/folder"
