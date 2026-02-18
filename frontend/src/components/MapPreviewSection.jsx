import { useRef, useEffect } from 'react'
import { motion, useInView } from 'framer-motion'
import { Maximize2, MapPin } from 'lucide-react'

import PantryMapClean from './PantryMapClean'
import useReducedMotion from '../hooks/useReducedMotion'

// Skeleton placeholder shown before map loads
function MapPreviewSkeleton() {
  return (
    <div className="h-[50vh] md:h-[60vh] bg-zinc-800/50 flex items-center justify-center" data-testid="map-skeleton">
      <div className="text-center">
        <MapPin className="w-10 h-10 text-zinc-600 mx-auto mb-3 animate-pulse" />
        <p className="text-sm text-zinc-500">Loading map...</p>
      </div>
    </div>
  )
}

export default function MapPreviewSection({ isInView, onBecomeVisible, pantries, onExpand }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '200px' })
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    if (inView && !isInView) {
      onBecomeVisible()
    }
  }, [inView, isInView, onBecomeVisible])

  const visible = inView || isInView

  const motionProps = reducedMotion
    ? {}
    : {
        initial: { opacity: 0, y: 40 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true },
        transition: { duration: 0.6 },
      }

  return (
    <section ref={ref} className="relative" data-testid="map-preview-section">
      {/* ── Dark section header (stays on dark bg) ── */}
      <div className="pt-24 pb-12 px-6">
        <motion.div {...motionProps} className="text-center">
          <h2 className="text-sm font-semibold text-emerald-400 uppercase tracking-widest mb-4">
            Live Network
          </h2>
          <p className="text-3xl md:text-4xl font-bold text-white">
            Explore Food Pantries Near You
          </p>
          <p className="mt-3 text-zinc-400 max-w-xl mx-auto">
            An interactive map of verified food pantries across major US cities.
            Click markers for details, hours, and directions.
          </p>
        </motion.div>
      </div>

      {/* ── Gradient transition: dark → white ── */}
      <div className="relative">
        {/* Top fade from dark into the map area */}
        <div className="h-24 bg-gradient-to-b from-zinc-950 via-zinc-900/80 to-zinc-800/0" />

        {/* Map card — floating over a soft white glow */}
        <div className="relative px-4 lg:px-8 -mt-8">
          {/* Soft glow behind the card */}
          <div className="absolute inset-x-0 top-8 bottom-8 mx-auto max-w-6xl rounded-3xl bg-white/[0.06] blur-2xl" />

          <motion.div
            {...motionProps}
            transition={reducedMotion ? undefined : { duration: 0.6, delay: 0.1 }}
            className="relative mx-auto max-w-6xl rounded-2xl overflow-hidden border border-white/10 shadow-2xl ring-1 ring-white/5"
          >
            {visible ? (
              <div className="relative">
                <PantryMapClean
                  pantries={pantries}
                  gestureHandling="cooperative"
                  className="h-[50vh] md:h-[60vh]"
                />

                {/* Expand button */}
                <button
                  onClick={onExpand}
                  className="absolute bottom-6 right-6 z-20 flex items-center gap-2 px-5 py-3 bg-emerald-500 hover:bg-emerald-400 text-white font-semibold rounded-xl shadow-lg transition-all hover:shadow-xl hover:scale-105 active:scale-100"
                  data-testid="expand-map-button"
                >
                  <Maximize2 className="w-5 h-5" />
                  <span>Explore Full Map</span>
                </button>

                {/* Cooperative mode hint */}
                <div className="absolute bottom-6 left-6 z-20 px-3 py-2 bg-zinc-900/70 backdrop-blur rounded-lg text-xs text-zinc-300 shadow-sm border border-white/10">
                  Use two fingers to zoom
                </div>
              </div>
            ) : (
              <MapPreviewSkeleton />
            )}
          </motion.div>
        </div>

        {/* Bottom fade from map area back into dark */}
        <div className="h-24 bg-gradient-to-b from-transparent to-zinc-950 mt-4" />
      </div>
    </section>
  )
}
