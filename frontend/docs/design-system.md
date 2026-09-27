# Component and styling guide

New pages should reuse the same structure as Recordings, Processing and Analysis. Keep feature-specific content inside these shared pieces rather than copying their markup.

| Need                                                  | Component                                                 |
| ----------------------------------------------------- | --------------------------------------------------------- |
| Page title, breadcrumb, action area and outer spacing | `Page`                                                    |
| Resizable and collapsible workspace panel             | `Workspace` and `SidePanel`                               |
| Standard secondary action                             | `Button`                                                  |
| Compact page tabs                                     | `Tabs`                                                    |
| Table panel, scrolling region and empty state         | `TablePanel`, `TableBody`, `EmptyState`, `SortableHeader` |
| Compact scrolling inside a panel                      | `ScrollArea`                                              |
| Search with matching geometry                         | `SearchField`                                             |
| Keyboard-accessible single-choice filter              | `FilterMenu`                                              |
| Selection with mixed state                            | `Checkbox`                                                |
| Confirmation and detail dialog                        | `Dialog`                                                  |
| Anchored overlay                                      | `Popover`                                                 |
| Ready, failure and neutral status text                | `StatusBadge`                                             |

`Page` owns the outer geometry. `Workspace` owns panel resizing and collapse; `SidePanel` uses its context. For a page without a side panel, use the page's feature workspace as Processing does. Keep table controls outside `TableBody` so they remain visible when rows scroll. Supply stable domain IDs as React keys.

## Tokens

Use the semantic variables in `src/styles/theme.css`. Changing a shared value should update all relevant controls.

| Purpose             | Tokens                                                                |
| ------------------- | --------------------------------------------------------------------- |
| Page and text       | `--background`, `--foreground`, `--muted-foreground`                  |
| Panels and controls | `--card`, `--secondary`, `--accent`                                   |
| Overlays            | `--popover`, `--popover-foreground`                                   |
| Dividers and focus  | `--border`, `--ring`                                                  |
| Status              | `--status-success`, `--status-error`; muted uses `--muted-foreground` |
| Destructive actions | `--destructive`                                                       |
| Spacing             | `--space-1` through `--space-4`: 4, 8, 12 and 16px                    |
| Control height      | `--control-height-compact`: 28px; `--control-height`: 30px            |
| Headers             | `--page-header-height`: 30px; `--panel-header-height`: 36px           |
| Corners             | `--radius-xs`, `--radius-sm`, `--radius-control`, `--radius-dialog`   |

Dark mode is selected by the `dark` class on the document root. The existing default is dark; no theme picker was added. Use semantic tokens in feature CSS so both appearances remain consistent.

`base.css` retains only the needed reset, utility and component foundations from the original design. Existing utility class names are preserved for fidelity, but new Tailwind-style class names are not generated automatically. Prefer shared components and named CSS rules. Put shared layout changes in `app.css` or `table.css`; put feature-specific changes in its stylesheet.

## Interaction conventions

Use accessible names for icon buttons, native buttons for actions, and links for navigation. Dialogs restore focus on dismissal. Filters support arrows, Home, End and Escape. Folder navigation keeps a roving tab stop. Pointer interactions must retain their keyboard equivalent. Respect reduced motion when adding animations.

Before changing shared styling, capture the approved UI, then inspect the visual comparison and run the affected browser tests. Check desktop and phone layouts in both themes. Avoid editing layout assertions merely to accept a regression.

Sortable data columns use `SortableHeader` with `useTableSort`: ascending, descending, then original order. Sorting is presentation state and never mutates queue priority. Calendar timestamps use `formatDateTime` (`DD/MM/YYYY, HH:mm`, Europe/Tallinn); graph Unix timestamps and durations retain their domain formats.

Single-line loading and empty states use `--muted-foreground`. Show initial loading
only when there is no cached content; never layer it over populated rows. Close
confirmation dialogs immediately, execute requests in the service, and surface
failures in the dismissible shell error. Keep actions protected against duplicate
submissions and restore optimistically dismissed data after request failure.

Use `ScrollArea` for panel content and `TableBody` for tables. The shared thumb
sits inside existing content padding without a reserved gutter. Preserve native
keyboard scrolling, touch scrolling and horizontal overflow.
