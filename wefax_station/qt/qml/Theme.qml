pragma Singleton
import QtQuick

/*
 * Theme.qml — Singleton thème "instrumentation radio" de Station WEFAX PRO
 *
 * Traduit fidèlement wefax_station/ui/theme.py en QML.
 * Usage : import "." as T  puis  T.Theme.bgRoot
 */
QtObject {
    id: root

    // ── Fonds ──────────────────────────────────────────────────────────────
    readonly property color bgRoot:    "#131922"   // fond fenêtre principale
    readonly property color bgPanel:   "#1b2430"   // panneaux / boîtes
    readonly property color bgSurface: "#232f3e"   // surfaces secondaires
    readonly property color bgCanvas:  "#0d131a"   // zone carte / spectre
    readonly property color bgOverlay: "#090d16"   // fond très sombre (barre statut)

    // ── Bordures ──────────────────────────────────────────────────────────
    readonly property color border:       "#2e3d4f"
    readonly property color borderActive: "#3b82f6"

    // ── Texte ─────────────────────────────────────────────────────────────
    readonly property color textPrimary: "#e6edf3"
    readonly property color textMuted:   "#9fb0c2"
    readonly property color textDim:     "#64748b"

    // ── Accent ────────────────────────────────────────────────────────────
    readonly property color accent:      "#2563eb"
    readonly property color accentHover: "#1d4ed8"
    readonly property color accentLight: "#3b82f6"

    // ── États sémantiques ─────────────────────────────────────────────────
    readonly property color okBg:   "#15803d"
    readonly property color okFg:   "#dcfce7"
    readonly property color warnBg: "#b45309"
    readonly property color warnFg: "#fef3c7"
    readonly property color errBg:  "#b91c1c"
    readonly property color errFg:  "#fee2e2"

    // ── Typographie ───────────────────────────────────────────────────────
    readonly property string fontMono:  "Consolas, 'Courier New', monospace"
    readonly property string fontUi:    "Segoe UI, Ubuntu, sans-serif"
    readonly property int    fontSizeXs: 9
    readonly property int    fontSizeSm: 10
    readonly property int    fontSizeMd: 11
    readonly property int    fontSizeLg: 13
    readonly property int    fontSizeXl: 16

    // ── Métriques ─────────────────────────────────────────────────────────
    readonly property int radiusSm: 4
    readonly property int radiusMd: 6
    readonly property int radiusLg: 10
    readonly property int spacing:  8
    readonly property int spacingLg: 16

    // ── Bargraphes qualité (8 niveaux) ───────────────────────────────────
    readonly property var qualityColors: [
        "#b91c1c",  // 0 — mauvais
        "#c2410c",
        "#b45309",
        "#a16207",
        "#4d7c0f",
        "#15803d",  // 5 — correct
        "#0e7490",
        "#1d4ed8",  // 7 — excellent
    ]

    // ── Couleurs par mode ─────────────────────────────────────────────────
    readonly property color wefaxColor:  "#2563eb"
    readonly property color rttyColor:   "#d97706"
    readonly property color navtexColor: "#7c3aed"
    readonly property color idleColor:   "#64748b"

    function modeColor(mode) {
        switch (mode) {
            case "WEFAX":  return wefaxColor
            case "RTTY":   return rttyColor
            case "NAVTEX": return navtexColor
            default:       return idleColor
        }
    }
}
