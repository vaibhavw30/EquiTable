import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import {
  Zap,
  MapPin,
  Brain,
  Radio,
  ArrowRight,
  ChevronDown,
  Terminal,
  Cpu,
  Database,
  CheckCircle,
} from 'lucide-react'
import { clsx } from 'clsx'

import useCities from '../hooks/useCities'

// Animated background grid
function GridBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {/* Gradient overlays */}
      <div className="absolute inset-0 bg-gradient-to-b from-zinc-950 via-transparent to-zinc-950" />
      <div className="absolute inset-0 bg-gradient-to-r from-zinc-950 via-transparent to-zinc-950" />

      {/* Animated grid lines */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(to right, #10b981 1px, transparent 1px),
            linear-gradient(to bottom, #10b981 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Floating orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl animate-pulse" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl animate-pulse delay-1000" />
    </div>
  )
}

// Live terminal feed (decorative)
function TerminalFeed() {
  const [lines, setLines] = useState([
    { text: '> Initializing autonomous agents...', type: 'system' },
    { text: '> Connected to multi-city food network', type: 'success' },
    { text: '> Scanning active nodes across 5 cities...', type: 'system' },
  ])

  useEffect(() => {
    const messages = [
      { text: '> [Atlanta] Midtown Assistance Center: ONLINE', type: 'success' },
      { text: '> [NYC] City Harvest: Status updated', type: 'success' },
      { text: '> [Chicago] Lakeview Pantry: ONLINE', type: 'success' },
      { text: '> Geospatial index optimized', type: 'system' },
      { text: '> [Houston] Food Bank: 200 families served', type: 'data' },
      { text: '> [LA] Regional Food Bank: Status updated', type: 'success' },
      { text: '> Running integrity checks...', type: 'system' },
    ]

    const interval = setInterval(() => {
      const msg = messages[Math.floor(Math.random() * messages.length)]
      setLines((prev) => [...prev.slice(-8), msg])
    }, 2000)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="font-mono text-xs space-y-1 opacity-60">
      {lines.map((line, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className={clsx(
            line.type === 'success' && 'text-emerald-400',
            line.type === 'system' && 'text-zinc-500',
            line.type === 'data' && 'text-blue-400'
          )}
        >
          {line.text}
        </motion.div>
      ))}
      <span className="inline-block w-2 h-4 bg-emerald-400 animate-pulse" />
    </div>
  )
}

// Hero section
function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center px-6">
      <div className="relative z-10 text-center max-w-4xl mx-auto">
        {/* Status badge */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-8"
        >
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_10px_rgba(52,211,153,0.8)]" />
          <span className="text-sm text-emerald-400 font-medium">System Online</span>
        </motion.div>

        {/* Main title */}
        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-6xl md:text-8xl font-bold tracking-tighter mb-6"
        >
          <span className="text-white">EQUI</span>
          <span className="text-emerald-400">TABLE</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="text-xl md:text-2xl text-zinc-400 mb-12 max-w-2xl mx-auto"
        >
          The Intelligence Layer for Food Security
        </motion.p>

        {/* CTA Button */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <Link
            to="/map"
            className="group relative inline-flex items-center gap-3 px-8 py-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-semibold text-lg transition-all duration-300 hover:shadow-[0_0_40px_rgba(52,211,153,0.4)]"
          >
            <Zap className="w-5 h-5" />
            LAUNCH SYSTEM
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />

            {/* Pulse ring */}
            <span className="absolute inset-0 rounded-xl bg-emerald-400 animate-ping opacity-20" />
          </Link>
        </motion.div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1 }}
          className="absolute bottom-12 left-1/2 -translate-x-1/2"
        >
          <ChevronDown className="w-6 h-6 text-zinc-600 animate-bounce" />
        </motion.div>
      </div>
    </section>
  )
}

// Mission section
function MissionSection() {
  const { scrollYProgress } = useScroll()
  const opacity = useTransform(scrollYProgress, [0.1, 0.3], [0, 1])

  return (
    <motion.section
      style={{ opacity }}
      className="relative py-32 px-6"
    >
      <div className="max-w-4xl mx-auto text-center">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-3xl md:text-5xl font-light leading-relaxed text-zinc-300"
        >
          <span className="text-emerald-400 font-semibold">"Hunger is not a scarcity problem;</span>
          <br />
          <span className="text-white">it's a logistics problem."</span>
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 }}
          className="mt-12 text-lg text-zinc-500 max-w-2xl mx-auto leading-relaxed"
        >
          America's cities have enough food to feed everyone, but the data is dark, disconnected, and decaying.
          EquiTable is the intelligence layer that bridges the gap — now live in Atlanta, NYC, LA, Chicago, and Houston.
        </motion.p>
      </div>
    </motion.section>
  )
}

// How it works section
function HowItWorksSection() {
  const steps = [
    {
      icon: Radio,
      title: 'SCRAPE',
      description: 'Autonomous agents continuously scan food pantry websites across major US cities, extracting real-time information.',
    },
    {
      icon: Brain,
      title: 'EXTRACT',
      description: 'AI parses unstructured data into actionable intelligence: hours, requirements, availability.',
    },
    {
      icon: MapPin,
      title: 'MAP',
      description: 'A live, geospatial interface connects people to resources based on their location and needs.',
    },
  ]

  return (
    <section className="relative py-32 px-6">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-sm font-semibold text-emerald-400 uppercase tracking-widest mb-4">
            How It Works
          </h2>
          <p className="text-3xl md:text-4xl font-bold text-white">
            Three Steps to Close the Loop
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-8">
          {steps.map((step, index) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.1 }}
              className="relative group"
            >
              <div className="p-8 rounded-2xl bg-zinc-900/50 border border-zinc-800/50 hover:border-emerald-500/30 transition-all duration-300">
                {/* Step number */}
                <div className="absolute -top-3 -left-3 w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-sm font-bold text-zinc-950">
                  {index + 1}
                </div>

                <step.icon className="w-10 h-10 text-emerald-400 mb-6" />
                <h3 className="text-xl font-bold text-white mb-3">{step.title}</h3>
                <p className="text-zinc-500 leading-relaxed">{step.description}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

// Stats section
function StatsSection({ cities }) {
  const totalPantries = cities.reduce((sum, c) => sum + c.count, 0)
  const cityCount = cities.length

  const stats = [
    { value: totalPantries > 0 ? String(totalPantries) : '35+', label: 'Active Pantries' },
    { value: cityCount > 0 ? String(cityCount) : '5', label: 'Cities' },
    { value: '5km', label: 'Radius Search' },
    { value: 'Real-time', label: 'Updates' },
  ]

  return (
    <section className="relative py-24 px-6 border-y border-zinc-800/50">
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((stat, index) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.1 }}
              className="text-center"
            >
              <p className="text-4xl md:text-5xl font-bold text-emerald-400 mb-2">
                {stat.value}
              </p>
              <p className="text-sm text-zinc-500 uppercase tracking-wider">
                {stat.label}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

// Terminal decoration section
function TerminalSection() {
  return (
    <section className="relative py-32 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="relative rounded-2xl bg-zinc-900/80 border border-zinc-800/50 overflow-hidden">
          {/* Terminal header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800/50 bg-zinc-900">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            <span className="text-xs text-zinc-600 ml-2">equitable-agent.sh</span>
          </div>

          {/* Terminal content */}
          <div className="p-6 min-h-[200px]">
            <TerminalFeed />
          </div>

          {/* Glow effect */}
          <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-emerald-500/5 to-transparent" />
        </div>
      </div>
    </section>
  )
}

// Final CTA section
function FinalCTASection() {
  return (
    <section className="relative py-32 px-6">
      <div className="max-w-3xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
            We don't just find food.
            <br />
            <span className="text-emerald-400">We close the loop.</span>
          </h2>

          <p className="text-lg text-zinc-500 mb-12 max-w-xl mx-auto">
            Join us in transforming food security infrastructure across America's cities with intelligent, autonomous systems.
          </p>

          <Link
            to="/map"
            className="inline-flex items-center gap-3 px-8 py-4 rounded-xl bg-white hover:bg-zinc-100 text-zinc-950 font-semibold text-lg transition-all"
          >
            <MapPin className="w-5 h-5" />
            Find Food Now
            <ArrowRight className="w-5 h-5" />
          </Link>
        </motion.div>
      </div>
    </section>
  )
}

// Footer
function Footer() {
  return (
    <footer className="border-t border-zinc-800/50 py-8 px-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-emerald-400" />
          <span className="font-bold text-white">EquiTable</span>
          <span className="text-zinc-600 text-sm">v1.0</span>
        </div>
        <p className="text-sm text-zinc-600">
          AI-Powered Food Rescue Agent
        </p>
      </div>
    </footer>
  )
}

// Main Landing Page
export default function LandingPage() {
  const { cities } = useCities()

  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-x-hidden">
      <GridBackground />
      <HeroSection />
      <MissionSection />
      <HowItWorksSection />
      <StatsSection cities={cities} />
      <TerminalSection />
      <FinalCTASection />
      <Footer />
    </div>
  )
}
