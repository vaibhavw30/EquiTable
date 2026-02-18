import { useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'

import MapExperience from './MapExperience'
import useReducedMotion from '../hooks/useReducedMotion'

export default function MapOverlay({ isOpen, onClose, initialPantries }) {
  const reducedMotion = useReducedMotion()

  // ESC key to close
  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose]
  )

  useEffect(() => {
    if (!isOpen) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, handleKeyDown])

  // Body scroll lock
  useEffect(() => {
    if (isOpen) {
      document.documentElement.style.overflow = 'hidden'
    } else {
      document.documentElement.style.overflow = ''
    }
    return () => {
      document.documentElement.style.overflow = ''
    }
  }, [isOpen])

  const backdropVariants = reducedMotion
    ? { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }

  const contentVariants = reducedMotion
    ? { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        initial: { scale: 0.95, opacity: 0 },
        animate: { scale: 1, opacity: 1 },
        exit: { scale: 0.95, opacity: 0 },
      }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          {...backdropVariants}
          transition={{ duration: reducedMotion ? 0 : 0.2 }}
          className="fixed inset-0 z-50 bg-white"
          data-testid="map-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Full map experience"
        >
          {/* Close button */}
          <motion.button
            initial={{ opacity: reducedMotion ? 1 : 0, scale: reducedMotion ? 1 : 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: reducedMotion ? 0 : 0.2 }}
            onClick={onClose}
            className="absolute top-4 right-4 z-[60] p-2 bg-white rounded-full shadow-lg border border-zinc-200 hover:bg-zinc-50 transition-colors"
            aria-label="Close map"
            data-testid="close-map-overlay"
          >
            <X className="w-5 h-5 text-zinc-700" />
          </motion.button>

          {/* Map experience */}
          <motion.div
            {...contentVariants}
            transition={reducedMotion ? { duration: 0 } : { type: 'spring', damping: 25, stiffness: 200 }}
            className="w-full h-full"
          >
            <MapExperience onClose={onClose} initialPantries={initialPantries} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
