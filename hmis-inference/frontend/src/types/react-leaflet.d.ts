// Module augmentation for react-leaflet — the runtime accepts these props
// (center, attribution, style) but the bundled TS definitions don't include
// them in this version. Augment here until upstream types catch up.

import 'react-leaflet'

declare module 'react-leaflet' {
  interface MapContainerProps {
    center?: unknown
    zoom?: number
    scrollWheelZoom?: boolean
    style?: unknown
  }
  interface TileLayerProps {
    attribution?: string
    url?: string
  }
  interface GeoJSONProps {
    data?: unknown
    style?: unknown
    onEachFeature?: unknown
  }
}
