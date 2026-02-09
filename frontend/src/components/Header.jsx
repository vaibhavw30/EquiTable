import { useState, useEffect } from 'react'
import { Search, X, Zap } from 'lucide-react'
import { clsx } from 'clsx'
import { motion, AnimatePresence } from 'framer-motion'

/**
 * Header - The command center header with logo and smart search
 *
 * Props:
 * - onSearch: Callback when search query changes
 * - pantryCount: Total pantries in system
 * - isOnline: System online status
 */
export default function Header({ onSearch, pantryCount = 0, isOnline = true }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [currentTime, setCurrentTime] = useState(new Date())

  // Update clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const handleSearch = (value) => {
    setSearchQuery(value)
    onSearch?.(value)
  }

  const clearSearch = () => {
    setSearchQuery('')
    onSearch?.('')
  }

  return (
    <header className="relative z-20">
      <div className="flex items-center justify-between gap-4 px-2">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Zap className="h-6 w-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Equi<span className="text-emerald-400">Table</span>
            </h1>
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-2 rounded-full bg-zinc-900/80 px-3 py-1.5 border border-zinc-800/50">
            <span
              className={clsx(
                'h-2 w-2 rounded-full',
                isOnline
                  ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-pulse'
                  : 'bg-red-500'
              )}
            />
            <span className="text-xs font-medium text-zinc-400">
              {isOnline ? 'SYSTEM ONLINE' : 'OFFLINE'}
            </span>
          </div>
        </div>

        {/* Center: Smart Search */}
        <div className="flex-1 max-w-md">
          <div
            className={clsx(
              'relative flex items-center rounded-xl transition-all duration-300',
              'bg-zinc-900/80 border',
              isFocused
                ? 'border-emerald-500/50 shadow-[0_0_20px_rgba(52,211,153,0.2)]'
                : 'border-zinc-800/50 hover:border-zinc-700/50'
            )}
          >
            <Search
              className={clsx(
                'absolute left-3 h-4 w-4 transition-colors',
                isFocused ? 'text-emerald-400' : 'text-zinc-500'
              )}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder="Search... try 'Open now' or 'No ID'"
              className={clsx(
                'w-full bg-transparent py-2.5 pl-10 pr-10',
                'text-sm text-white placeholder:text-zinc-600',
                'focus:outline-none'
              )}
            />
            <AnimatePresence>
              {searchQuery && (
                <motion.button
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  onClick={clearSearch}
                  className="absolute right-3 p-0.5 rounded-full hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300"
                >
                  <X className="h-3.5 w-3.5" />
                </motion.button>
              )}
            </AnimatePresence>
          </div>

          {/* Search hints */}
          <AnimatePresence>
            {isFocused && !searchQuery && (
              <motion.div
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                className="absolute mt-2 flex gap-2"
              >
                {['Open now', 'No ID', 'Midtown'].map((hint) => (
                  <button
                    key={hint}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      handleSearch(hint)
                    }}
                    className="px-2 py-1 text-xs rounded-md bg-zinc-800/80 text-zinc-400 hover:text-emerald-400 hover:bg-zinc-800 transition-colors"
                  >
                    {hint}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right: Time & Stats */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">
              Atlanta, GA
            </p>
            <p className="text-sm font-mono text-zinc-300">
              {currentTime.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
              })}
            </p>
          </div>
          <div className="h-8 w-px bg-zinc-800" />
          <div className="text-right">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">
              Nodes Active
            </p>
            <p className="text-sm font-bold text-emerald-400">{pantryCount}</p>
          </div>
        </div>
      </div>

      {/* Bottom border glow */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-emerald-500/30 to-transparent" />
    </header>
  )
}
