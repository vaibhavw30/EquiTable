import { Target, Cpu, MapPin, ArrowRight } from 'lucide-react'
import { clsx } from 'clsx'

/**
 * MissionCard - Displays the EquiTable mission statement
 */
export default function MissionCard({ className }) {
  return (
    <div
      className={clsx(
        'relative overflow-hidden rounded-2xl',
        'bg-zinc-900/60 backdrop-blur-xl',
        'border border-zinc-800/50',
        className
      )}
    >
      {/* Gradient accent line at top */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-emerald-500/50 to-transparent" />

      <div className="p-5 space-y-4">
        {/* Title */}
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-emerald-400" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-emerald-400">
            The Mission
          </h3>
        </div>

        {/* Main quote */}
        <blockquote className="text-sm leading-relaxed text-zinc-300">
          <span className="text-emerald-400 font-semibold">
            "Hunger is not a scarcity problem; it's a logistics problem."
          </span>
        </blockquote>

        {/* Body text */}
        <p className="text-xs leading-relaxed text-zinc-500">
          Atlanta has enough food to feed everyone, but the data is dark,
          disconnected, and decaying. EquiTable is the intelligence layer that
          bridges the gap.
        </p>

        {/* Feature highlights */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Cpu className="h-3 w-3 text-emerald-500/70" />
            <span>Autonomous agents audit 24/7</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <MapPin className="h-3 w-3 text-emerald-500/70" />
            <span>Live, life-saving map</span>
          </div>
        </div>

        {/* Tagline */}
        <div className="pt-3 border-t border-zinc-800/50">
          <p className="text-xs font-medium text-zinc-500">
            We don't just find food.{' '}
            <span className="text-emerald-400">We close the loop.</span>
          </p>
        </div>
      </div>
    </div>
  )
}
