use crate::customglyph::*;
use crate::termwindow::box_model::*;
use crate::termwindow::{UIItem, UIItemType};
use crate::utilsprites::RenderMetrics;
use crate::workspace_sidebar::WorkspaceSidebarItem;
use config::{Dimension, DimensionContext, TabBarColors};
use window::color::LinearRgba;

/// "+" plus glyph for the new-workspace button (two outline strokes).
const PLUS_BUTTON: &[Poly] = &[
    Poly {
        path: &[
            PolyCommand::MoveTo(BlockCoord::Frac(1, 2), BlockCoord::Zero),
            PolyCommand::LineTo(BlockCoord::Frac(1, 2), BlockCoord::One),
        ],
        intensity: BlockAlpha::Full,
        style: PolyStyle::Outline,
    },
    Poly {
        path: &[
            PolyCommand::MoveTo(BlockCoord::Zero, BlockCoord::Frac(1, 2)),
            PolyCommand::LineTo(BlockCoord::One, BlockCoord::Frac(1, 2)),
        ],
        intensity: BlockAlpha::Full,
        style: PolyStyle::Outline,
    },
];

impl crate::TermWindow {
    pub fn invalidate_workspace_sidebar(&mut self) {
        self.workspace_sidebar_computed.take();
    }

    pub fn build_workspace_sidebar(&self) -> anyhow::Result<ComputedElement> {
        let font = self.fonts.title_font()?;
        let metrics = RenderMetrics::with_font_metrics(&font.metrics());
        let sidebar_width = self.left_sidebar_width();
        let border = self.get_os_border();

        // The fancy tab bar occupies the top strip to the RIGHT of the sidebar.
        // With the retro tab bar we cannot shift it, so start the sidebar below
        // the tab-bar strip in that case (documented fallback). Only inset when
        // the retro bar is at the top.
        let top_inset = if self.show_tab_bar
            && !self.config.use_fancy_tab_bar
            && !self.config.tab_bar_at_bottom
        {
            self.tab_bar_pixel_height().unwrap_or(0.)
        } else {
            0.
        };

        // Colors derived from the existing palette so we need no new config.
        let frame = &self.config.window_frame;
        let bg = if self.focused.is_some() {
            frame.active_titlebar_bg
        } else {
            frame.inactive_titlebar_bg
        }
        .to_linear();
        let fg = if self.focused.is_some() {
            frame.active_titlebar_fg
        } else {
            frame.inactive_titlebar_fg
        }
        .to_linear();

        let tab_bar_colors = self
            .config
            .resolved_palette
            .tab_bar
            .clone()
            .unwrap_or_else(TabBarColors::default);
        let active_tab = tab_bar_colors.active_tab();
        let hover_tab = tab_bar_colors.inactive_tab_hover();
        let active_bg = active_tab.bg_color.to_linear();
        let active_fg = active_tab.fg_color.to_linear();
        let inactive_bg = bg;
        let inactive_fg = fg;
        let hover_bg = hover_tab.bg_color.to_linear();
        let hover_fg = hover_tab.fg_color.to_linear();

        let make_colors = |bg: LinearRgba, fg: LinearRgba| ElementColors {
            border: BorderColor::default(),
            bg: bg.into(),
            text: fg.into(),
        };

        let row_padding = BoxDimension {
            left: Dimension::Cells(0.5),
            right: Dimension::Cells(0.5),
            top: Dimension::Cells(0.25),
            bottom: Dimension::Cells(0.25),
        };

        // Total height available to the strip (inside the OS border, below any
        // retro tab-bar inset).
        let avail_height = self.dimensions.pixel_height as f32
            - (border.top + border.bottom).get() as f32
            - top_inset;

        let width_context = DimensionContext {
            dpi: self.dimensions.dpi as f32,
            pixel_max: self.dimensions.pixel_width as f32,
            pixel_cell: metrics.cell_size.width as f32,
        };
        let height_context = DimensionContext {
            dpi: self.dimensions.dpi as f32,
            pixel_max: self.dimensions.pixel_height as f32,
            pixel_cell: metrics.cell_size.height as f32,
        };

        // A row's rendered width is its content width plus its horizontal
        // padding. To keep the row (and its highlight background) flush with the
        // strip instead of spilling past the right edge, the content must be
        // sized to `sidebar_width - horizontal_padding`.
        let row_h_pad = row_padding.left.evaluate_as_pixels(width_context)
            + row_padding.right.evaluate_as_pixels(width_context);
        let row_width = (sidebar_width - row_h_pad).max(0.);

        // Geometry for the "+" button. It sits directly below the last row and
        // matches a normal row's overall size: a row's rendered box is
        // `sidebar_width` wide and `cell_h + top/bottom padding` tall. The plus
        // glyph is kept small and centered by inflating symmetric padding around
        // it to fill that box (a bare Poly's content width ignores min_width, so
        // padding is what sizes and centers it).
        let cell_h = metrics.cell_size.height as f32;
        let row_v_pad = row_padding.top.evaluate_as_pixels(height_context)
            + row_padding.bottom.evaluate_as_pixels(height_context);
        let row_box_height = cell_h + row_v_pad;
        let plus_size = cell_h / 2.;
        let plus_pad_x = ((sidebar_width - plus_size) / 2.).max(0.);
        let plus_pad_y = ((row_box_height - plus_size) / 2.).max(0.);

        // Build the workspace rows and the trailing "+" button separately so we
        // can pin the button to the bottom of the strip.
        let mut rows: Vec<Element> = vec![];
        let mut plus_button: Option<Element> = None;
        for entry in self.workspace_sidebar.items() {
            match &entry.item {
                WorkspaceSidebarItem::Workspace { .. } => {
                    let (row_bg, row_fg) = if entry.active {
                        (active_bg, active_fg)
                    } else {
                        (inactive_bg, inactive_fg)
                    };
                    rows.push(
                        Element::new(&font, ElementContent::Text(entry.name.clone()))
                            .display(DisplayType::Block)
                            .item_type(UIItemType::WorkspaceSidebar(entry.item.clone()))
                            .padding(row_padding)
                            .min_width(Some(Dimension::Pixels(row_width)))
                            .colors(make_colors(row_bg, row_fg))
                            .hover_colors(Some(make_colors(hover_bg, hover_fg))),
                    );
                }
                WorkspaceSidebarItem::NewButton => {
                    plus_button = Some(
                        Element::new(
                            &font,
                            ElementContent::Poly {
                                line_width: metrics.underline_height.max(2),
                                poly: SizedPoly {
                                    poly: PLUS_BUTTON,
                                    width: Dimension::Pixels(plus_size),
                                    height: Dimension::Pixels(plus_size),
                                },
                            },
                        )
                        .display(DisplayType::Block)
                        .item_type(UIItemType::WorkspaceSidebar(entry.item.clone()))
                        .padding(BoxDimension {
                            left: Dimension::Pixels(plus_pad_x),
                            right: Dimension::Pixels(plus_pad_x),
                            top: Dimension::Pixels(plus_pad_y),
                            bottom: Dimension::Pixels(plus_pad_y),
                        })
                        .colors(make_colors(inactive_bg, inactive_fg))
                        .hover_colors(Some(make_colors(hover_bg, hover_fg))),
                    );
                }
            }
        }

        let content_bounds = euclid::rect(
            border.left.get() as f32,
            border.top.get() as f32 + top_inset,
            sidebar_width,
            avail_height,
        );

        // The "+" button stacks directly below the last workspace row; the
        // container's min_height fills the rest of the strip with background.
        let mut children = rows;
        if let Some(button) = plus_button {
            children.push(button);
        }

        let root = Element::new(&font, ElementContent::Children(children))
            .display(DisplayType::Block)
            .min_width(Some(Dimension::Pixels(sidebar_width)))
            .min_height(Some(Dimension::Pixels(avail_height)))
            .colors(make_colors(bg, fg));

        let computed = self.compute_element(
            &LayoutContext {
                height: height_context,
                width: width_context,
                bounds: content_bounds,
                metrics: &metrics,
                gl_state: self.render_state.as_ref().unwrap(),
                zindex: 10,
            },
            &root,
        )?;

        Ok(computed)
    }

    pub fn paint_workspace_sidebar(&self) -> anyhow::Result<Vec<UIItem>> {
        let computed = self
            .workspace_sidebar_computed
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("paint_workspace_sidebar called but cache is None"))?;
        let ui_items = computed.ui_items();
        let gl_state = self.render_state.as_ref().unwrap();
        self.render_element(computed, gl_state, None)?;
        Ok(ui_items)
    }
}
