"""Tests for AssetReference filename uniqueness via _accept_plugin_fields."""

from schemas.design_spec import AssetReference


class TestAssetFilenameUniqueness:
    """Validate that AssetReference produces unique filenames from node_id."""

    def test_same_nodename_different_nodeids_produce_unique_filenames(self):
        a = AssetReference(**{"nodeName": "Vector", "nodeId": "1:403"})
        b = AssetReference(**{"nodeName": "Vector", "nodeId": "1:404"})
        assert a.filename != b.filename
        assert "1-403" in a.filename
        assert "1-404" in b.filename

    def test_many_duplicate_nodenames_all_unique(self):
        assets = [
            AssetReference(**{"nodeName": "Vector", "nodeId": f"1:{400 + i}"})
            for i in range(67)
        ]
        filenames = [a.filename for a in assets]
        assert len(set(filenames)) == 67

    def test_simple_nodeid_sanitization(self):
        a = AssetReference(**{"nodeName": "vector", "nodeId": "1:403"})
        assert a.filename == "vector-1-403.png"

    def test_complex_nodeid_sanitization(self):
        a = AssetReference(**{
            "nodeName": "icon",
            "nodeId": "I1:492;4124:6218;6:161",
        })
        # All non-alphanumeric chars replaced with dashes
        assert "I1-492-4124-6218-6-161" in a.filename
        assert a.filename.endswith(".png")

    def test_nodeid_with_only_special_chars(self):
        a = AssetReference(**{"nodeName": "shape", "nodeId": ":::"})
        # After sanitizing, all chars become '-', then stripped → empty safe_id
        # With empty safe_id, the node_id branch may produce "shape-.png" or similar
        # Key: no crash
        assert isinstance(a.filename, str)
        assert len(a.filename) > 0

    def test_empty_nodeid_no_suffix_appended(self):
        a = AssetReference(**{"nodeName": "hero", "nodeId": ""})
        # Empty node_id → filename should not get a suffix
        assert a.filename == "hero.png"

    def test_empty_filename_no_crash(self):
        # Both nodeName and filename missing → filename defaults to ""
        a = AssetReference(**{"nodeId": "1:1"})
        assert isinstance(a.filename, str)

    def test_filename_without_extension_gets_png(self):
        a = AssetReference(**{"nodeName": "hero-image", "nodeId": "1:1"})
        assert a.filename.endswith(".png")
        assert "hero-image" in a.filename

    def test_filename_with_svg_extension_preserved(self):
        a = AssetReference(**{"filename": "logo.svg", "nodeId": "1:2"})
        assert a.filename.endswith(".svg")
        assert "1-2" in a.filename

    def test_filename_with_multiple_dots(self):
        a = AssetReference(**{"filename": "my.icon.file.png", "nodeId": "1:3"})
        # rsplit(".", 1) splits on last dot only
        assert a.filename.endswith(".png")
        assert "my.icon.file" in a.filename
        assert "1-3" in a.filename


class TestAssetFilenameEdgeCases:
    """Edge cases for filename generation."""

    def test_very_long_filename(self):
        long_name = "A" * 200
        a = AssetReference(**{"nodeName": long_name, "nodeId": "1:1"})
        assert isinstance(a.filename, str)
        assert long_name in a.filename

    def test_unicode_filename(self):
        a = AssetReference(**{"nodeName": "アイコン", "nodeId": "1:5"})
        assert isinstance(a.filename, str)
        assert "アイコン" in a.filename

    def test_filename_with_spaces(self):
        a = AssetReference(**{"nodeName": "my icon", "nodeId": "2:10"})
        # Spaces in name preserved; only nodeId sanitized
        assert "my icon" in a.filename
        assert "2-10" in a.filename

    def test_nodeid_appears_exactly_once(self):
        a = AssetReference(**{"nodeName": "btn", "nodeId": "3:7"})
        # The suffix "3-7" should appear exactly once
        assert a.filename.count("3-7") == 1

    def test_backend_format_collision_scenario(self):
        """Two assets constructed via backend field names with same filename but different node_ids."""
        a = AssetReference(node_id="10:1", filename="icon.png")
        b = AssetReference(node_id="10:2", filename="icon.png")
        assert a.filename != b.filename
