"""
Tests for the graph layer (Step 5).

Structure
---------
TestGraphModels          — dataclass construction
TestGraphServiceUnit     — pure service functions on hand-built nx graphs
TestGetDependencies      — get_dependencies / get_dependents
TestCallersCallees       — get_callers / get_callees
TestFindPath             — find_path
TestFileGraph            — get_file_dependencies
TestRepositoryGraphOp    — get_repository_graph
TestBuildRepositoryGraph — DB-backed builder (requires db_session fixture)
TestRepositoryIsolation  — isolation: two repos, no cross-contamination
TestRealFixture          — end-to-end: ingest simple_repo → graph traversal
"""

from __future__ import annotations

import uuid
from pathlib import Path

import networkx as nx
import pytest

from app.services.graph import (
    FileDependency,
    GraphEdge,
    GraphNode,
    PathResult,
    RepositoryGraph,
    build_repository_graph,
    find_path,
    get_callees,
    get_callers,
    get_dependents,
    get_dependencies,
    get_file_dependencies,
    get_repository_graph,
)
from app.services.ingestion import ingest_repository


# ---------------------------------------------------------------------------
# Helpers: construct hand-built graphs without a database
# ---------------------------------------------------------------------------

SIMPLE_REPO = Path(__file__).parent / "fixtures" / "ingestion" / "simple_repo"


def _make_node(
    graph: nx.MultiDiGraph,
    *,
    symbol_id: uuid.UUID | None = None,
    name: str = "fn",
    qualified_name: str | None = None,
    symbol_type: str = "function",
    file_id: uuid.UUID | None = None,
    file_path: str = "module.py",
    start_line: int = 1,
    end_line: int = 5,
) -> uuid.UUID:
    sid = symbol_id or uuid.uuid4()
    fid = file_id or uuid.uuid4()
    graph.add_node(
        sid,
        name=name,
        qualified_name=qualified_name or name,
        symbol_type=symbol_type,
        file_id=fid,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
    )
    return sid


def _make_edge(
    graph: nx.MultiDiGraph,
    src: uuid.UUID,
    tgt: uuid.UUID,
    *,
    relationship_type: str = "CALLS",
    confidence: float | None = 0.9,
) -> uuid.UUID:
    rel_id = uuid.uuid4()
    graph.add_edge(
        src,
        tgt,
        key=rel_id,
        relationship_id=rel_id,
        relationship_type=relationship_type,
        confidence=confidence,
    )
    return rel_id


# ---------------------------------------------------------------------------
# TestGraphModels
# ---------------------------------------------------------------------------

class TestGraphModels:
    def test_graph_node_fields(self):
        sid = uuid.uuid4()
        fid = uuid.uuid4()
        node = GraphNode(
            symbol_id=sid,
            name="authenticate",
            qualified_name="authenticate",
            symbol_type="function",
            file_id=fid,
            file_path="services/auth.py",
            start_line=10,
            end_line=20,
        )
        assert node.symbol_id == sid
        assert node.name == "authenticate"
        assert node.file_path == "services/auth.py"

    def test_graph_edge_fields(self):
        rid = uuid.uuid4()
        src = uuid.uuid4()
        tgt = uuid.uuid4()
        edge = GraphEdge(
            relationship_id=rid,
            source_symbol_id=src,
            target_symbol_id=tgt,
            relationship_type="CALLS",
            confidence=0.9,
        )
        assert edge.relationship_type == "CALLS"
        assert edge.confidence == 0.9

    def test_path_result_not_found(self):
        src = uuid.uuid4()
        tgt = uuid.uuid4()
        r = PathResult(found=False, source_symbol_id=src, target_symbol_id=tgt)
        assert not r.found
        assert r.steps == []

    def test_file_dependency_fields(self):
        sfid = uuid.uuid4()
        tfid = uuid.uuid4()
        fd = FileDependency(
            source_file_id=sfid,
            source_file_path="a.py",
            target_file_id=tfid,
            target_file_path="b.py",
            relationship_types=["CALLS", "IMPORTS"],
            edge_count=3,
        )
        assert fd.edge_count == 3
        assert "CALLS" in fd.relationship_types


# ---------------------------------------------------------------------------
# TestGetDependencies
# ---------------------------------------------------------------------------

class TestGetDependencies:
    def test_direct_dependency(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        _make_edge(g, a, b, relationship_type="CALLS")

        deps = get_dependencies(g, a)
        assert len(deps) == 1
        assert deps[0].symbol_id == b

    def test_multiple_dependencies(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        c = _make_node(g, name="c")
        _make_edge(g, a, b)
        _make_edge(g, a, c)

        deps = get_dependencies(g, a)
        ids = {d.symbol_id for d in deps}
        assert ids == {b, c}

    def test_filtered_by_relationship_type(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        c = _make_node(g, name="c")
        _make_edge(g, a, b, relationship_type="CALLS")
        _make_edge(g, a, c, relationship_type="IMPORTS")

        # Only CALLS
        deps = get_dependencies(g, a, relationship_types=["CALLS"])
        assert len(deps) == 1
        assert deps[0].symbol_id == b

    def test_symbol_not_in_graph(self):
        g = nx.MultiDiGraph()
        assert get_dependencies(g, uuid.uuid4()) == []

    def test_no_outgoing_edges(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        assert get_dependencies(g, a) == []

    def test_deduplication_multiple_edges_same_target(self):
        # Two edges from A → B (different relationship types)
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        _make_edge(g, a, b, relationship_type="CALLS")
        _make_edge(g, a, b, relationship_type="IMPORTS")

        # With no filter, B should appear exactly once
        deps = get_dependencies(g, a)
        assert len(deps) == 1
        assert deps[0].symbol_id == b

    def test_direct_dependents(self):
        g = nx.MultiDiGraph()
        caller1 = _make_node(g, name="caller1")
        caller2 = _make_node(g, name="caller2")
        target = _make_node(g, name="target")
        _make_edge(g, caller1, target)
        _make_edge(g, caller2, target)

        deps = get_dependents(g, target)
        ids = {d.symbol_id for d in deps}
        assert ids == {caller1, caller2}

    def test_dependents_filtered(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        c = _make_node(g, name="c")
        _make_edge(g, a, c, relationship_type="CALLS")
        _make_edge(g, b, c, relationship_type="INHERITS")

        # Only CALLS
        deps = get_dependents(g, c, relationship_types=["CALLS"])
        assert len(deps) == 1
        assert deps[0].symbol_id == a

    def test_dependents_symbol_not_in_graph(self):
        g = nx.MultiDiGraph()
        assert get_dependents(g, uuid.uuid4()) == []


# ---------------------------------------------------------------------------
# TestCallersCallees
# ---------------------------------------------------------------------------

class TestCallersCallees:
    def test_callers(self):
        g = nx.MultiDiGraph()
        fn = _make_node(g, name="fn")
        c1 = _make_node(g, name="c1")
        c2 = _make_node(g, name="c2")
        _make_edge(g, c1, fn, relationship_type="CALLS")
        _make_edge(g, c2, fn, relationship_type="CALLS")

        callers = get_callers(g, fn)
        ids = {n.symbol_id for n in callers}
        assert ids == {c1, c2}

    def test_callers_ignores_non_calls(self):
        g = nx.MultiDiGraph()
        fn = _make_node(g, name="fn")
        importer = _make_node(g, name="importer")
        _make_edge(g, importer, fn, relationship_type="IMPORTS")

        assert get_callers(g, fn) == []

    def test_callees(self):
        g = nx.MultiDiGraph()
        fn = _make_node(g, name="fn")
        c1 = _make_node(g, name="c1")
        c2 = _make_node(g, name="c2")
        _make_edge(g, fn, c1, relationship_type="CALLS")
        _make_edge(g, fn, c2, relationship_type="CALLS")
        # Also an IMPORTS edge that should NOT be in callees
        c3 = _make_node(g, name="c3")
        _make_edge(g, fn, c3, relationship_type="IMPORTS")

        callees = get_callees(g, fn)
        ids = {n.symbol_id for n in callees}
        assert ids == {c1, c2}

    def test_callers_empty_graph(self):
        g = nx.MultiDiGraph()
        assert get_callers(g, uuid.uuid4()) == []

    def test_callees_no_calls(self):
        g = nx.MultiDiGraph()
        fn = _make_node(g, name="fn")
        assert get_callees(g, fn) == []


# ---------------------------------------------------------------------------
# TestFindPath
# ---------------------------------------------------------------------------

class TestFindPath:
    def test_direct_path(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        _make_edge(g, a, b, relationship_type="CALLS")

        result = find_path(g, a, b)
        assert result.found
        assert len(result.steps) == 2
        assert result.steps[0].node.symbol_id == a
        assert result.steps[0].edge is None
        assert result.steps[1].node.symbol_id == b
        assert result.steps[1].edge is not None
        assert result.steps[1].edge.relationship_type == "CALLS"

    def test_multi_hop_path(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        c = _make_node(g, name="c")
        _make_edge(g, a, b, relationship_type="CALLS")
        _make_edge(g, b, c, relationship_type="CALLS")

        result = find_path(g, a, c)
        assert result.found
        assert len(result.steps) == 3
        node_ids = [s.node.symbol_id for s in result.steps]
        assert node_ids == [a, b, c]

    def test_no_path(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        # No edge between a and b

        result = find_path(g, a, b)
        assert not result.found
        assert result.steps == []

    def test_source_equals_target(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")

        result = find_path(g, a, a)
        assert result.found
        assert len(result.steps) == 1
        assert result.steps[0].node.symbol_id == a
        assert result.steps[0].edge is None

    def test_source_not_in_graph(self):
        g = nx.MultiDiGraph()
        b = _make_node(g, name="b")

        result = find_path(g, uuid.uuid4(), b)
        assert not result.found

    def test_target_not_in_graph(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")

        result = find_path(g, a, uuid.uuid4())
        assert not result.found

    def test_both_not_in_graph(self):
        g = nx.MultiDiGraph()
        result = find_path(g, uuid.uuid4(), uuid.uuid4())
        assert not result.found

    def test_multiple_paths_returns_shortest(self):
        # a → b → c  (length 2)
        # a → c      (length 1)
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        c = _make_node(g, name="c")
        _make_edge(g, a, b)
        _make_edge(g, b, c)
        _make_edge(g, a, c)  # shortcut

        result = find_path(g, a, c)
        assert result.found
        # Shortest path is a → c (2 steps)
        assert len(result.steps) == 2

    def test_directed_no_reverse(self):
        # a → b, but not b → a
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        _make_edge(g, a, b)

        # b cannot reach a
        result = find_path(g, b, a)
        assert not result.found

    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        result = find_path(g, uuid.uuid4(), uuid.uuid4())
        assert not result.found


# ---------------------------------------------------------------------------
# TestFileGraph
# ---------------------------------------------------------------------------

class TestFileGraph:
    def _two_file_graph(self):
        """Return (graph, file_a_id, file_b_id, sym_a1, sym_a2, sym_b1, sym_b2)."""
        g = nx.MultiDiGraph()
        fid_a = uuid.uuid4()
        fid_b = uuid.uuid4()
        a1 = _make_node(g, name="a1", file_id=fid_a, file_path="a.py")
        a2 = _make_node(g, name="a2", file_id=fid_a, file_path="a.py")
        b1 = _make_node(g, name="b1", file_id=fid_b, file_path="b.py")
        b2 = _make_node(g, name="b2", file_id=fid_b, file_path="b.py")
        return g, fid_a, fid_b, a1, a2, b1, b2

    def test_cross_file_dependency(self):
        g, fid_a, fid_b, a1, _, b1, _ = self._two_file_graph()
        _make_edge(g, a1, b1, relationship_type="CALLS")

        deps = get_file_dependencies(g, fid_a)
        assert len(deps) == 1
        assert deps[0].target_file_id == fid_b
        assert deps[0].edge_count == 1
        assert "CALLS" in deps[0].relationship_types

    def test_multiple_symbol_edges_collapse_to_one_file_dep(self):
        # Two different symbol pairs cross the same file boundary
        g, fid_a, fid_b, a1, a2, b1, b2 = self._two_file_graph()
        _make_edge(g, a1, b1, relationship_type="CALLS")
        _make_edge(g, a2, b2, relationship_type="IMPORTS")

        deps = get_file_dependencies(g, fid_a)
        assert len(deps) == 1
        assert deps[0].edge_count == 2
        assert set(deps[0].relationship_types) == {"CALLS", "IMPORTS"}

    def test_self_file_excluded(self):
        g = nx.MultiDiGraph()
        fid = uuid.uuid4()
        a = _make_node(g, name="a", file_id=fid, file_path="a.py")
        b = _make_node(g, name="b", file_id=fid, file_path="a.py")
        _make_edge(g, a, b)

        deps = get_file_dependencies(g, fid)
        assert deps == []

    def test_file_not_in_graph(self):
        g = nx.MultiDiGraph()
        assert get_file_dependencies(g, uuid.uuid4()) == []

    def test_file_with_no_outgoing_cross_edges(self):
        # File A only has incoming edges
        g, fid_a, fid_b, a1, _, b1, _ = self._two_file_graph()
        _make_edge(g, b1, a1, relationship_type="CALLS")

        deps = get_file_dependencies(g, fid_a)
        assert deps == []

    def test_three_files(self):
        g = nx.MultiDiGraph()
        fid_a = uuid.uuid4()
        fid_b = uuid.uuid4()
        fid_c = uuid.uuid4()
        a = _make_node(g, name="a", file_id=fid_a, file_path="a.py")
        b = _make_node(g, name="b", file_id=fid_b, file_path="b.py")
        c = _make_node(g, name="c", file_id=fid_c, file_path="c.py")
        _make_edge(g, a, b)
        _make_edge(g, a, c)

        deps = get_file_dependencies(g, fid_a)
        assert len(deps) == 2
        target_ids = {d.target_file_id for d in deps}
        assert target_ids == {fid_b, fid_c}


# ---------------------------------------------------------------------------
# TestRepositoryGraphOp
# ---------------------------------------------------------------------------

class TestRepositoryGraphOp:
    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        repo_id = uuid.uuid4()
        rg = get_repository_graph(g, repo_id)
        assert isinstance(rg, RepositoryGraph)
        assert rg.repository_id == repo_id
        assert rg.nodes == []
        assert rg.edges == []

    def test_nodes_and_edges_present(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        _make_edge(g, a, b, relationship_type="CALLS")

        repo_id = uuid.uuid4()
        rg = get_repository_graph(g, repo_id)
        assert len(rg.nodes) == 2
        assert len(rg.edges) == 1
        assert rg.edges[0].relationship_type == "CALLS"

    def test_node_metadata_preserved(self):
        g = nx.MultiDiGraph()
        sid = uuid.uuid4()
        _make_node(g, symbol_id=sid, name="myfn", qualified_name="MyClass.myfn",
                   symbol_type="method", file_path="mod.py", start_line=5, end_line=10)

        rg = get_repository_graph(g, uuid.uuid4())
        assert len(rg.nodes) == 1
        n = rg.nodes[0]
        assert n.symbol_id == sid
        assert n.name == "myfn"
        assert n.qualified_name == "MyClass.myfn"
        assert n.symbol_type == "method"
        assert n.start_line == 5

    def test_edge_metadata_preserved(self):
        g = nx.MultiDiGraph()
        a = _make_node(g, name="a")
        b = _make_node(g, name="b")
        rel_id = _make_edge(g, a, b, relationship_type="INHERITS", confidence=1.0)

        rg = get_repository_graph(g, uuid.uuid4())
        assert len(rg.edges) == 1
        e = rg.edges[0]
        assert e.relationship_id == rel_id
        assert e.relationship_type == "INHERITS"
        assert e.confidence == 1.0


# ---------------------------------------------------------------------------
# TestBuildRepositoryGraph — DB-backed
# ---------------------------------------------------------------------------

class TestBuildRepositoryGraph:
    async def test_empty_repository(self, db_session):
        from app.db.models import Repository as RepositoryModel
        repo_id = uuid.uuid4()
        repo = RepositoryModel(
            id=repo_id,
            name="empty",
            status="ready",
        )
        db_session.add(repo)
        await db_session.flush()

        graph = await build_repository_graph(repo_id, db_session)
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0

    async def test_graph_from_simple_repo(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        # simple_repo has 3 files with symbols
        assert graph.number_of_nodes() > 0
        assert graph.number_of_edges() > 0

    async def test_node_metadata_from_db(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        # Every node should have the required metadata keys
        for nid in graph.nodes():
            data = graph.nodes[nid]
            assert "name" in data
            assert "qualified_name" in data
            assert "symbol_type" in data
            assert "file_id" in data
            assert "file_path" in data
            assert "start_line" in data
            assert "end_line" in data

    async def test_edge_metadata_from_db(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        for src, tgt, key, data in graph.edges(data=True, keys=True):
            assert "relationship_id" in data
            assert "relationship_type" in data
            # confidence may be None but key must exist
            assert "confidence" in data


# ---------------------------------------------------------------------------
# TestRepositoryIsolation — two ingestions must not share nodes
# ---------------------------------------------------------------------------

class TestRepositoryIsolation:
    async def test_isolation_two_ingestions(self, db_session):
        """Nodes from repo A must not appear in the graph of repo B."""
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="repo_a")
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="repo_b")
        await db_session.commit()

        graph_a = await build_repository_graph(result_a.repository_id, db_session)
        graph_b = await build_repository_graph(result_b.repository_id, db_session)

        ids_a = set(graph_a.nodes())
        ids_b = set(graph_b.nodes())

        # Both graphs should have nodes
        assert len(ids_a) > 0
        assert len(ids_b) > 0

        # No overlap — different ingestions produce different UUIDs
        assert ids_a.isdisjoint(ids_b), "Repositories share graph nodes — isolation violated"

    async def test_traversal_in_a_does_not_see_b(self, db_session):
        """get_dependencies() on a node from repo A never returns a node from repo B."""
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="iso_a")
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="iso_b")
        await db_session.commit()

        graph_a = await build_repository_graph(result_a.repository_id, db_session)
        graph_b = await build_repository_graph(result_b.repository_id, db_session)

        ids_b = set(graph_b.nodes())

        for nid in graph_a.nodes():
            deps = get_dependencies(graph_a, nid)
            for dep in deps:
                assert dep.symbol_id not in ids_b, (
                    f"Node {dep.symbol_id} from repo B appeared in traversal of repo A"
                )


# ---------------------------------------------------------------------------
# TestRealFixture — end-to-end: ingest → graph → traversal
# ---------------------------------------------------------------------------

class TestRealFixture:
    async def test_user_inherits_entity(self, db_session):
        """User INHERITS Entity relationship should appear in the graph."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        # Find User and Entity nodes
        user_id = None
        entity_id = None
        for nid, data in graph.nodes(data=True):
            if data["qualified_name"] == "User":
                user_id = nid
            if data["qualified_name"] == "Entity":
                entity_id = nid

        assert user_id is not None, "User symbol not found in graph"
        assert entity_id is not None, "Entity symbol not found in graph"

        # User depends on (inherits from) Entity
        deps = get_dependencies(graph, user_id, relationship_types=["INHERITS"])
        dep_ids = {d.symbol_id for d in deps}
        assert entity_id in dep_ids, "User does not INHERIT Entity in graph"

    async def test_entity_is_inherited_by_user(self, db_session):
        """get_dependents on Entity should return User (via INHERITS)."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        user_id = None
        entity_id = None
        for nid, data in graph.nodes(data=True):
            if data["qualified_name"] == "User":
                user_id = nid
            if data["qualified_name"] == "Entity":
                entity_id = nid

        assert user_id is not None
        assert entity_id is not None

        dependents = get_dependents(graph, entity_id, relationship_types=["INHERITS"])
        dep_ids = {d.symbol_id for d in dependents}
        assert user_id in dep_ids

    async def test_run_calls_process_and_format_output(self, db_session):
        """run() in main.py should CALL process and format_output from utils.py."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        run_id = None
        process_id = None
        format_id = None
        for nid, data in graph.nodes(data=True):
            qn = data["qualified_name"]
            if qn == "run":
                run_id = nid
            elif qn == "process":
                process_id = nid
            elif qn == "format_output":
                format_id = nid

        assert run_id is not None, "run symbol not found"

        callees = get_callees(graph, run_id)
        callee_ids = {c.symbol_id for c in callees}

        assert process_id is not None, "process symbol not found"
        assert format_id is not None, "format_output symbol not found"
        assert process_id in callee_ids, "run does not call process"
        assert format_id in callee_ids, "run does not call format_output"

    async def test_process_has_callers(self, db_session):
        """process() should have at least one caller (run)."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        process_id = None
        run_id = None
        for nid, data in graph.nodes(data=True):
            if data["qualified_name"] == "process":
                process_id = nid
            if data["qualified_name"] == "run":
                run_id = nid

        assert process_id is not None
        assert run_id is not None

        callers = get_callers(graph, process_id)
        caller_ids = {c.symbol_id for c in callers}
        assert run_id in caller_ids

    async def test_find_path_run_to_process(self, db_session):
        """find_path(run, process) should return a direct one-hop path."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        run_id = None
        process_id = None
        for nid, data in graph.nodes(data=True):
            if data["qualified_name"] == "run":
                run_id = nid
            if data["qualified_name"] == "process":
                process_id = nid

        assert run_id is not None
        assert process_id is not None

        path = find_path(graph, run_id, process_id)
        assert path.found
        assert len(path.steps) == 2
        assert path.steps[0].node.symbol_id == run_id
        assert path.steps[1].node.symbol_id == process_id
        assert path.steps[1].edge.relationship_type == "CALLS"

    async def test_find_path_no_path(self, db_session):
        """There is no path from Entity to run (different files, no dependency)."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        entity_id = None
        run_id = None
        for nid, data in graph.nodes(data=True):
            if data["qualified_name"] == "Entity":
                entity_id = nid
            if data["qualified_name"] == "run":
                run_id = nid

        assert entity_id is not None
        assert run_id is not None

        path = find_path(graph, entity_id, run_id)
        assert not path.found

    async def test_file_dependencies_main_py(self, db_session):
        """main.py depends on utils.py (calls process, format_output)."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)

        # Find file_id for main.py
        main_file_id = None
        utils_file_id = None
        for nid, data in graph.nodes(data=True):
            if "main.py" in data.get("file_path", ""):
                main_file_id = data["file_id"]
            if "utils.py" in data.get("file_path", ""):
                utils_file_id = data["file_id"]

        assert main_file_id is not None, "main.py not found in graph nodes"
        assert utils_file_id is not None, "utils.py not found in graph nodes"

        deps = get_file_dependencies(graph, main_file_id)
        target_ids = {d.target_file_id for d in deps}
        assert utils_file_id in target_ids, "main.py does not depend on utils.py in file graph"

    async def test_get_repository_graph_has_all_symbols(self, db_session):
        """get_repository_graph should return the same node count as the ingestion result."""
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        graph = await build_repository_graph(result.repository_id, db_session)
        rg = get_repository_graph(graph, result.repository_id)

        assert len(rg.nodes) == result.total_symbols
        assert rg.repository_id == result.repository_id
