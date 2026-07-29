from __future__ import annotations

import inspect
import unittest

import mocaviz.app as app_module


class BdPhotometryParallaxTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_bootstrap_objects_include_requested_parallax_fields(self):
        payload = self.client.get("/api/bootstrap?mock=1").get_json()

        self.assertTrue(payload["ok"])
        row = payload["catalog"]["objects"][0]
        self.assertIsInstance(row["parallax_mas"], float)
        self.assertIsInstance(row["parallax_mas_error"], float)
        self.assertTrue(row["parallax_ref"])
        self.assertTrue(any(candidate["parallax_mas"] is None for candidate in payload["catalog"]["objects"]))

    def test_object_query_uses_only_the_adopted_parallax(self):
        source = " ".join(inspect.getsource(app_module._load_bootstrap_from_db).split())

        self.assertIn("dplx.parallax_mas", source)
        self.assertIn("dplx.parallax_mas_unc AS parallax_mas_error", source)
        self.assertIn("dplx.bibcode AS parallax_ref", source)
        self.assertIn(
            "LEFT JOIN data_parallaxes dplx ON dplx.moca_oid = dst.moca_oid AND dplx.adopted = 1",
            source,
        )

    def test_table_and_exports_include_parallax_columns(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        table_block = script.split("function renderTable(rowIds)", 1)[1].split(
            "function bdTableMarkerHtml", 1
        )[0]
        export_block = script.split("const exportColumns = [", 1)[1].split("];", 1)[0]

        for column in ("parallax_mas", "parallax_mas_error", "parallax_ref"):
            self.assertIn(f'tableColumn("{column}")', table_block)
            self.assertIn(f'"{column}"', export_block)

    def test_photometric_distance_option_is_the_inverse_parallax_filter(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        build_rows_block = script.split("function buildRows()", 1)[1].split(
            "function associationHighlightForObject", 1
        )[0]

        self.assertIn('id="include-photdist" type="checkbox"', html)
        self.assertNotIn('id="only-trig-parallaxes"', html)
        self.assertNotIn("only-trig-parallaxes", script)
        self.assertIn('params.delete("trigplx")', script)
        self.assertNotIn("function updatePhotdistControl", script)
        self.assertIn('state.manualPhotdistChoice = params.has("photdist")', script)
        self.assertIn(
            'el["include-photdist"].checked = state.manualPhotdistChoice\n'
            '    ? asBool(params.get("photdist"))\n'
            '    : false;',
            script,
        )
        self.assertIn("function applyPhotometricDistanceDefault()", script)
        self.assertIn("const checked = false;", script)
        self.assertIn("const includePhotdist = includePhotometricDistances()", build_rows_block)
        self.assertIn("const usePhotdistForAxes = usePhotometricDistancesForAxes()", build_rows_block)
        self.assertIn(
            "is_photometric_distance: usePhotdistForAxes &&",
            build_rows_block,
        )
        self.assertIn(
            "if (!includePhotdist && !Number.isFinite(numericValue(object.parallax_mas))) continue;",
            build_rows_block,
        )

    def test_rich_gravity_categories_are_wired_to_js_controls_and_markers(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        classifier = script.split("function richGravityCategoryForObject(object)", 1)[1].split(
            "function normalizeGravityText",
            1,
        )[0]

        self.assertIn('id="rich-gravity-categories" type="checkbox"', html)
        self.assertIn("Use richer gravity class categories", html)
        self.assertIn("<code>richgravity</code>", html)
        self.assertIn('el["rich-gravity-categories"].checked = asBool(params.get("richgravity"))', script)
        self.assertIn('params.set("richgravity", el["rich-gravity-categories"].checked ? "1" : "0")', script)
        for category in (
            "field",
            "beta",
            "gamma",
            "pec_red",
            "pec_blue",
            "pec_other",
            "sd",
            "d_sd",
            "esd",
            "usd",
        ):
            self.assertIn(f'return "{category}"', classifier)
        self.assertLess(classifier.index('return "usd"'), classifier.index('return "pec_red"'))
        self.assertLess(classifier.index('return "pec_red"'), classifier.index('return "gamma"'))
        self.assertIn("richGravityCategoriesRequested() ? row.rich_gravity_category : row.age_sample", script)
        self.assertIn("richGravityCategoryLegendOrder", script)
        self.assertIn("richGravityCategorySymbols", script)
        self.assertIn('field: "Field grav. / α"', script)
        self.assertIn('beta: "Int. grav. / β"', script)
        self.assertIn('gamma: "Very low grav. / γ"', script)
        self.assertIn("rich-gravity-20260716a", html)

    def test_capped_selection_prioritizes_objects_with_all_axis_photometry(self):
        args = {
            "spt_range": "L0+",
            "photspt": "1",
            "max_objects": "5000",
            "xaxis_type": "spectral_type",
            "yaxis_type": "color",
            "yaxis_value_1": "euclid_ymag",
            "yaxis_value_2": "euclid_hmag",
        }

        priority_sql, priority_params = app_module._axis_photometry_priority_sql(args)
        selection_sql = app_module._selected_oids_subquery_sql(
            "dst.adopted = 1",
            "\n            LIMIT 5000",
            priority_sql,
        )

        self.assertEqual(
            priority_params,
            {
                "axis_photometry_priority_0": "euclid_ymag",
                "axis_photometry_priority_1": "euclid_hmag",
            },
        )
        self.assertEqual(priority_sql.count("EXISTS ("), 2)
        self.assertIn("dp_priority_0.moca_oid = dst.moca_oid", priority_sql)
        self.assertIn("dp_priority_1.moca_oid = dst.moca_oid", priority_sql)
        self.assertIn("dp_priority_0.magnitude_unc IS NOT NULL", priority_sql)
        order_sql = selection_sql.split("ORDER BY", 1)[1]
        self.assertLess(order_sql.index("CASE WHEN"), order_sql.index("dst.spectral_type_number"))
        self.assertLess(order_sql.index("CASE WHEN"), order_sql.index("LIMIT 5000"))

    def test_large_object_selection_joins_spectra_instead_of_expanding_an_oid_list(self):
        source = " ".join(inspect.getsource(app_module._load_bootstrap_from_db).split())

        self.assertIn("if _should_use_selected_oid_join(selected_oids):", source)
        self.assertIn("STRAIGHT_JOIN moca_spectra ms ON ms.moca_oid = selected_oids.moca_oid", source)
        self.assertIn('spectra_oid_filter = "1 = 1"', source)
        self.assertIn('spectra_source_from_sql = "moca_spectra ms"', source)
        self.assertIn("spectra_oid_filter = _oid_filter_sql(\"ms\", selected_oids)", source)
        self.assertIn("), spectra_params)", source)

    def test_empirical_sequence_fit_control_and_plot_traces(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = self.client.get("/js/bd-colors").get_data(as_text=True)

        self.assertIn('id="fit-sequence"', html)
        self.assertIn('id="fit-sequence-status"', html)
        self.assertIn('id="sequence-fit-smoothing"', html)
        self.assertIn('id="sequence-fit-selected-only" type="checkbox"', html)
        self.assertIn("Fit selected data points only", html)
        self.assertLess(
            html.index('id="sequence-fit-smoothing"'),
            html.index('id="sequence-fit-selected-only"'),
        )
        self.assertLess(
            html.index('id="sequence-fit-selected-only"'),
            html.index('id="fit-sequence"'),
        )
        self.assertIn('class="sequence-fit-ticks" aria-hidden="true"', html)
        self.assertEqual(html.split('class="sequence-fit-ticks"', 1)[1].split("</div>", 1)[0].count("<span>"), 16)
        self.assertIn('id="export-sequence-csv"', html)
        self.assertIn("Export sequence as CSV", html)
        self.assertIn('value="2.5"', html)
        self.assertIn("function fittedSequenceModel(rows)", script)
        self.assertIn("const sequenceFitEvaluationStep = 0.1", script)
        self.assertIn("const sequenceFitPostSmoothingFraction = 1 / 3", script)
        self.assertIn("const sequenceFitRenderDelayMs = 1000", script)
        self.assertIn("function scheduleSequenceFitRender()", script)
        self.assertIn('el["sequence-fit-smoothing"].addEventListener("change", () => {', script)
        self.assertIn('textContent = "Release the smoothing slider to refit."', script)
        self.assertIn('el["sequence-fit-selected-only"].checked = asBool(params.get("sequence_selected_only"))', script)
        self.assertIn('params.set("sequence_selected_only", sequenceFitSelectedOnly() ? "1" : "0")', script)
        self.assertIn("const selectedRowIds = selectedOnly ? new Set(state.selectedRowIds) : null", script)
        self.assertIn("(!selectedRowIds || selectedRowIds.has(row.row_id))", script)
        self.assertIn("const minObjectsPerWindow = selectedOnly ? 1 : sequenceFitMinObjectsPerWindow", script)
        self.assertIn("if (weightedRows.length < minObjectsPerWindow) continue", script)
        self.assertIn("function applyPlotSelection(rowIds)", script)
        self.assertIn("if (state.sequenceFitEnabled && sequenceFitSelectedOnly())", script)
        self.assertIn("function unbindPlotEvents()", script)
        self.assertIn("unbindPlotEvents();", script)
        self.assertIn('el.plot.removeAllListeners("plotly_selected")', script)
        self.assertIn('el.plot.removeAllListeners("plotly_deselect")', script)
        self.assertIn("if (selected.has(rowId)) selected.delete(rowId)", script)
        self.assertIn("else selected.add(rowId)", script)
        self.assertIn("function smoothSequenceFitPoints(points, width, xIsSpt, yIsSpt)", script)
        self.assertIn("item.point.xMad ** 2", script)
        self.assertIn("item.point.yMad ** 2", script)
        self.assertIn("sequenceFitWindowWeight", script)
        self.assertIn("function weightedMedian(values, weights)", script)
        self.assertIn("function weightedMedianAbsoluteDeviation", script)
        self.assertIn("function weightedComedian", script)
        self.assertNotIn("weightedSampleStandardDeviation", script)
        self.assertNotIn("weightedSampleCovariance", script)
        self.assertIn("fittedSequenceRibbonMask", script)
        self.assertIn("sequenceFitParametricRibbonGeometry", script)
        self.assertIn("sequenceFitParametricBandCoordinates", script)
        self.assertIn("sequenceFitSmoothNormals", script)
        self.assertIn("sequenceFitRobustSmoothValues", script)
        self.assertIn("sequenceFitRibbonBounds", script)
        self.assertIn("sequenceFitContinuousNormals", script)
        self.assertIn("withSequenceFitGapSeparators", script)
        self.assertLess(
            script.index("traces.push(selectedPointTrace(selectedMarkerRows(plottedRows)))"),
            script.index("if (sequenceFitTraces.line) traces.push(sequenceFitTraces.line)"),
        )
        self.assertIn("fittedSequenceLineCoordinates(model.points, model.selectedOnly)", script)
        self.assertIn("withSequenceFitGapSeparators(model.points, hoverText, model.selectedOnly)", script)
        self.assertIn("function withSequenceFitGapSeparators(points, values, connectGaps = false)", script)
        self.assertIn('const yReversed = el["y-axis-type"]?.value === "absolute_magnitude"', script)
        self.assertIn("const image = band ? null : fittedSequenceRibbonMask(model)", script)
        self.assertIn("if (hasTeffAxis()) return sequenceFitParametricBandCoordinates(model)", script)
        self.assertIn("geometry.upper[index + 1]", script)
        self.assertIn("geometry.lower[index + 1]", script)
        self.assertIn("y: yReversed ? bounds.yMin : bounds.yMax", script)
        self.assertIn('fill: "toself"', script)
        self.assertIn('fillcolor: "rgba(128,128,128,0.7)"', script)
        self.assertIn("opacity: 0.7", script)
        self.assertIn('name: "Sequence ±1 MAD"', script)
        self.assertIn('line: { color: "#000000", width: sequenceFitLineWidth }', script)
        self.assertIn("xIsSpt ? subtype : weightedMedian(xValues, weights)", script)
        self.assertIn("yIsSpt ? subtype : weightedMedian(yValues, weights)", script)
        self.assertIn("function fittedSequenceCsv(model = state.sequenceFitModel)", script)
        self.assertIn('"fitted_x_scatter"', script)
        self.assertIn('"fitted_y_scatter"', script)
        self.assertIn('downloadBlob(csv, "moca_fitted_sequence.csv"', script)

    def test_azul_backyard_worlds_sample_is_private_only_and_highlighted(self):
        private_args = {
            "dbase": "mocadb_private_tables",
            "user": "management",
            "azul_byw_sample": "1",
        }
        public_args = {
            "dbase": "mocadb",
            "user": "public",
            "azul_byw_sample": "1",
        }

        private_range_sql, *_ = app_module._range_sql(private_args)
        public_range_sql, *_ = app_module._range_sql(public_args)
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = self.client.get("/js/bd-colors").get_data(as_text=True)

        self.assertTrue(app_module._include_azul_byw_sample(private_args))
        self.assertFalse(app_module._include_azul_byw_sample(public_args))
        self.assertNotIn("pcat_azul_byw_sample_jul16_2026", private_range_sql)
        self.assertNotIn("pcat_azul_byw_sample_jul16_2026", public_range_sql)
        self.assertEqual(private_range_sql, public_range_sql)
        priority_sql, _ = app_module._selection_priority_sql({
            **private_args,
            "xaxis_type": "color",
            "xaxis_value_1": "simple:J",
            "xaxis_value_2": "simple:K",
        })
        self.assertIn("azul_byw_priority.moca_oid = dst.moca_oid", priority_sql)
        self.assertLess(priority_sql.index("azul_byw_priority"), priority_sql.index("dp_priority_0"))
        self.assertIn('id="azul-byw-sample-line" class="checkline" hidden', html)
        self.assertIn('id="display-azul-byw-sample" type="checkbox"', html)
        self.assertIn("Display Azul's Backyard Worlds sample", html)
        self.assertIn("function updateAzulBywSampleControl()", script)
        self.assertIn("line.hidden = !hasLoadedCatalog || !privateData", script)
        self.assertIn("Number(object.azul_byw_sample || 0) === 1", script)

    def test_highlighted_points_have_thick_gold_error_bars(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        trace_block = script.split("function highlightedPointTraces(rows)", 1)[1].split(
            "function selectedMarkerRows",
            1,
        )[0]

        self.assertIn('errorBarTraces(rows, 0.42, "highlighted-errors"', trace_block)
        self.assertIn('color: "#d69e00"', trace_block)
        self.assertIn("forceVisible: true", trace_block)
        self.assertIn("thickness: 3", trace_block)
        self.assertIn("width: 5", trace_block)
        self.assertEqual(trace_block.count('type: "scatter"'), 3)

        error_trace_block = script.split("function errorBarTrace(rows", 1)[1].split(
            "function hasFiniteError",
            1,
        )[0]
        self.assertIn('type: style.type || "scattergl"', error_trace_block)

    def test_highlighted_points_use_above_data_overlays(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        layout_block = script.split("const layout = {", 1)[1].split(
            "const plotCanvasKey",
            1,
        )[0]
        shape_block = script.split("function highlightedPointShapes(rows)", 1)[1].split(
            "function selectedMarkerRows",
            1,
        )[0]
        html = (app_module.STATIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("shapes: highlightedPointShapes(highlightedRows)", layout_block)
        self.assertIn('xsizemode: "pixel"', shape_block)
        self.assertIn('ysizemode: "pixel"', shape_block)
        self.assertIn('layer: "above"', shape_block)
        self.assertIn('type: "path"', shape_block)
        self.assertIn("path: highlightedStarPath", shape_block)
        self.assertIn('fillcolor: "#d69e00"', shape_block)
        self.assertIn('line: { color: "#111", width: 2.5 }', shape_block)
        self.assertNotIn("highlightedPointAnnotations", script)
        self.assertIn("highlight-layer-20260729b", html)

    def test_error_bars_follow_marker_colors_with_lower_opacity(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        error_block = script.split("function errorBarTraces(rows", 1)[1].split(
            "function errorBarTrace(rows",
            1,
        )[0]

        self.assertIn("errorBarColorForRow(row, ageDomain)", error_block)
        self.assertIn("colorWithOpacity(color, opacity)", error_block)
        self.assertIn('traces.push(...errorBarTraces(good, 0.18, "default-good-errors"))', script)
        self.assertIn("return Math.max(0.06, opacity * 0.18)", script)

    def test_useful_ranges_exclude_deemphasized_points_and_pad_y(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        draw_block = script.split("function drawPlot(rows, plottedRows", 1)[1].split(
            "function currentPlotCanvasKey",
            1,
        )[0]
        percentile_block = script.split("function percentileRange(rows, field)", 1)[1].split(
            "function rangeWithAbsoluteMagnitudeYDwarfs",
            1,
        )[0]
        padding_block = script.split("function rangeWithAdditionalYAxisPadding(range, field)", 1)[1].split(
            "function rangeWithAbsoluteMagnitudeYDwarfs",
            1,
        )[0]

        self.assertIn("const additionalYAxisPaddingFraction = 0.15", script)
        self.assertIn("const yAxisLowerQuantile = 0.01", script)
        self.assertIn("const yAxisUpperQuantile = 0.99", script)
        self.assertIn("const rangeRows = automaticRangeRows(plottedRows)", draw_block)
        self.assertIn('x: percentileRange(rangeRows, "x")', draw_block)
        self.assertIn('y: percentileRange(rangeRows, "y")', draw_block)
        self.assertNotIn('percentileRange(plottedRows, "y")', draw_block)
        self.assertIn("const good = rows.filter((row) => !row.noisy)", script)
        self.assertIn('field === "y" ? yAxisLowerQuantile : 0.02', percentile_block)
        self.assertIn('field === "y" ? yAxisUpperQuantile : 0.98', percentile_block)
        self.assertIn("rangeWithAdditionalYAxisPadding(usefulRange, field)", percentile_block)
        self.assertIn("rangeWithNonnegativeSpectralIndexFloor(paddedRange, values, field)", percentile_block)
        self.assertIn('if (field !== "y") return range', padding_block)
        self.assertIn("span * additionalYAxisPaddingFraction", padding_block)
        self.assertIn("[range[0] - padding, range[1] + padding]", padding_block)
        self.assertIn('el["y-axis-type"]?.value !== "spectral_index"', script)
        self.assertIn("[Math.max(0, range[0]), range[1]]", script)

    def test_spectral_index_axes_add_calculation_links_to_selection_table(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        explorer_script = (app_module.STATIC_DIR / "spectral_index_explorer.js").read_text(encoding="utf-8")
        table_block = script.split("function renderTable(rowIds)", 1)[1].split(
            "function bdTableMarkerHtml",
            1,
        )[0]

        self.assertIn("showIndexCalculationLinks", table_block)
        self.assertIn('"index calculation"', table_block)
        self.assertIn("spectralIndexCalculationLinksHtml(row)", table_block)
        self.assertIn("View index calculation", script)
        self.assertIn('new URL("spectral-index-explorer", appBaseUrl)', script)
        self.assertIn('params.set("moca_specid", input.moca_specid)', script)
        self.assertIn('params.set("moca_siid", input.moca_siid)', script)
        self.assertIn('moca_siid: row.moca_siid', script)
        self.assertIn('params.get("moca_siid")', explorer_script)
        self.assertIn('params.set("q", sieState.requestedMocaSiid)', explorer_script)
        self.assertIn('String(item.moca_siid || "").toLowerCase() === requested', explorer_script)


if __name__ == "__main__":
    unittest.main()
