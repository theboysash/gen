import { useState, useEffect } from 'react'
import axios from 'axios'
import './App.css'

const GOOGLE_API_KEY = import.meta.env.VITE_GOOGLE_API_KEY

const INDUSTRIES = [
  'Dentists', 'Orthodontists', 'Physiotherapists', 'Chiropractors',
  'Attorneys', 'Accountants', 'Plastic Surgeons', 'Aesthetic Clinics',
  'Plumbers', 'Electricians', 'Driving Schools', 'Veterinarians',
  'Personal Trainers', 'Wedding Photographers', 'Real Estate Agents',
]

const SUBURBS = [
  'Sandton', 'Rosebank', 'Randburg', 'Fourways', 'Midrand',
  'Bedfordview', 'Edenvale', 'Boksburg', 'Bryanston', 'Morningside',
  'Parktown', 'Melrose', 'Illovo', 'Northcliff', 'Roodepoort',
  'Alberton', 'Germiston', 'Benoni', 'Centurion', 'Kempton Park',
  'Soweto', 'Krugersdorp', 'Kyalami', 'Greenside', 'Linden',
]

interface Lead {
  place_id: string
  name: string
  address: string
  phone: string
  website: string
  has_website: boolean
  rating: number | null
  total_reviews: number | null
}

interface ScoreResult {
  screenshot_base64: string
  technical_score: number
  visual_score: number
  combined_score: number
  issues: string[]
  ai_summary: string
  needs_revamp: boolean
  mobile_responsive: boolean
  ssl: boolean
  error?: string
}

type CallStatus = 'uncalled' | 'interested' | 'not_interested' | 'callback'

const STATUS_CONFIG = {
  uncalled:       { label: 'Not Called',     color: '#666',    bg: 'rgba(100,100,100,0.1)' },
  interested:     { label: 'Interested',     color: '#c8f135', bg: 'rgba(200,241,53,0.1)'  },
  not_interested: { label: 'Not Interested', color: '#ff4d4d', bg: 'rgba(255,77,77,0.1)'   },
  callback:       { label: 'Call Back',      color: '#ff9f43', bg: 'rgba(255,159,67,0.1)'  },
}

export default function App() {
  const [industry, setIndustry]       = useState('')
  const [suburb, setSuburb]           = useState('')
  const [leads, setLeads]             = useState<Lead[]>([])
  const [loading, setLoading]         = useState(false)
  const [loadingMsg, setLoadingMsg]   = useState('')
  const [error, setError]             = useState('')
  const [statuses, setStatuses]       = useState<Record<string, CallStatus>>({})
  const [notes, setNotes]             = useState<Record<string, string>>({})
  const [editingNote, setEditingNote] = useState<string | null>(null)
  const [scores, setScores]           = useState<Record<string, ScoreResult>>({})
  const [scoringId, setScoringId]     = useState<string | null>(null)
  const [scoringQueue, setScoringQueue] = useState<Lead[]>([])
  const [scoringProgress, setScoringProgress] = useState({ done: 0, total: 0 })

  // Auto-score queue — runs sequentially whenever scoringQueue changes
  useEffect(() => {
    if (scoringQueue.length === 0) return

    const runNext = async () => {
      const lead = scoringQueue[0]
      setScoringId(lead.place_id)

      try {
        const res = await axios.get(
          `http://localhost:5000/score?url=${encodeURIComponent(lead.website)}`,
          { timeout: 30000 }
        )
        setScores(prev => ({ ...prev, [lead.place_id]: res.data }))
      } catch (e) {
        console.error(`Score error for ${lead.name}:`, e)
        // Mark as errored so we don't get stuck
        setScores(prev => ({
          ...prev,
          [lead.place_id]: {
            screenshot_base64: '',
            technical_score: 0,
            visual_score: 0,
            combined_score: 0,
            issues: [],
            ai_summary: 'Could not analyse website',
            needs_revamp: false,
            mobile_responsive: false,
            ssl: false,
            error: 'Failed to analyse',
          }
        }))
      } finally {
        setScoringProgress(prev => ({ ...prev, done: prev.done + 1 }))
        setScoringQueue(prev => prev.slice(1)) // remove first item, triggers next
        setScoringId(null)
      }
    }

    runNext()
  }, [scoringQueue])

  const fetchLeads = async () => {
    if (!industry || !suburb) return
    setLoading(true)
    setError('')
    setLeads([])
    setScores({})
    setStatuses({})
    setScoringQueue([])
    setScoringProgress({ done: 0, total: 0 })

    try {
      const url = 'https://places.googleapis.com/v1/places:searchText'
      const headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_API_KEY,
        'X-Goog-FieldMask': 'places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount',
      }

      let allPlaces: any[] = []

      setLoadingMsg('Fetching page 1...')
      const res1 = await axios.post(url, {
        textQuery: `${industry} in ${suburb} Johannesburg`,
        pageSize: 20,
      }, { headers })

      const places1 = res1.data.places || []
      allPlaces = [...places1]

      const pageToken = res1.data.nextPageToken
      if (pageToken) {
        setLoadingMsg('Fetching page 2...')
        await new Promise(r => setTimeout(r, 3000))
        const res2 = await axios.post(url, { pageToken }, { headers })
        allPlaces = [...allPlaces, ...(res2.data.places || [])]
      }

      const parsed: Lead[] = allPlaces.map((p: any) => ({
        place_id:      p.id,
        name:          p.displayName?.text || 'Unknown',
        address:       p.formattedAddress || '',
        phone:         p.nationalPhoneNumber || '',
        website:       p.websiteUri || '',
        has_website:   !!p.websiteUri,
        rating:        p.rating || null,
        total_reviews: p.userRatingCount || null,
      }))

      parsed.sort((a, b) => {
        if (!a.has_website && b.has_website) return -1
        if (a.has_website && !b.has_website) return 1
        return (b.rating || 0) - (a.rating || 0)
      })

      setLeads(parsed)

      // Queue up all leads that have a website for auto-scoring
      const toScore = parsed.filter(l => l.has_website)
      setScoringProgress({ done: 0, total: toScore.length })
      setScoringQueue(toScore)

    } catch (e: any) {
      setError(e?.response?.data?.error?.message || 'Something went wrong')
    } finally {
      setLoading(false)
      setLoadingMsg('')
    }
  }

  const setStatus = (id: string, status: CallStatus) => {
    setStatuses(prev => ({ ...prev, [id]: status }))
  }

  const stats = {
    total:      leads.length,
    no_website: leads.filter(l => !l.has_website).length,
    interested: Object.values(statuses).filter(s => s === 'interested').length,
    called:     Object.values(statuses).filter(s => s !== 'uncalled').length,
  }

  const analysisComplete = scoringProgress.total > 0 &&
    scoringProgress.done === scoringProgress.total

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-bracket">[</span>
            LEADGEN
            <span className="logo-bracket">]</span>
          </div>
          <p className="tagline">Joburg small business lead intelligence</p>
        </div>
      </header>

      {/* Controls */}
      <div className="controls-wrap">
        <div className="controls">
          <div className="select-group">
            <label>INDUSTRY</label>
            <select value={industry} onChange={e => setIndustry(e.target.value)}>
              <option value="">Select industry...</option>
              {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
          </div>

          <div className="select-group">
            <label>SUBURB</label>
            <select value={suburb} onChange={e => setSuburb(e.target.value)}>
              <option value="">Select suburb...</option>
              {SUBURBS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <button
            className="generate-btn"
            onClick={fetchLeads}
            disabled={!industry || !suburb || loading}
          >
            {loading ? <span className="spinner" /> : 'GENERATE LEADS'}
          </button>
        </div>

        {/* Stats */}
        {leads.length > 0 && (
          <div className="stats-bar">
            <div className="stat"><span className="stat-num">{stats.total}</span><span className="stat-label">Total</span></div>
            <div className="stat accent"><span className="stat-num">{stats.no_website}</span><span className="stat-label">No Website</span></div>
            <div className="stat green"><span className="stat-num">{stats.interested}</span><span className="stat-label">Interested</span></div>
            <div className="stat"><span className="stat-num">{stats.called}</span><span className="stat-label">Called</span></div>
          </div>
        )}

        {/* Analysis progress bar */}
        {scoringProgress.total > 0 && (
          <div className="analysis-progress">
            <div className="analysis-progress-header">
              <span>
                {analysisComplete
                  ? `✓ Analysis complete — ${scoringProgress.total} sites scored`
                  : `Analysing websites... ${scoringProgress.done}/${scoringProgress.total}`}
              </span>
              {!analysisComplete && <span className="spinner" />}
            </div>
            <div className="progress-bar-track">
              <div
                className="progress-bar-fill"
                style={{ width: `${(scoringProgress.done / scoringProgress.total) * 100}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Error */}
      {error && <div className="error-msg">⚠ {error}</div>}

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="loading-dots"><span /><span /><span /></div>
          <p>{loadingMsg || `Scanning ${suburb} for ${industry}...`}</p>
        </div>
      )}

      {/* Results */}
      {leads.length > 0 && (
        <div className="results">
          <div className="results-header">
            <span>{leads.length} leads found in {suburb}</span>
            <span className="results-hint">Sorted: no website first</span>
          </div>

          <div className="leads-grid">
            {leads.map(lead => {
              const status  = statuses[lead.place_id] || 'uncalled'
              const cfg     = STATUS_CONFIG[status]
              const note    = notes[lead.place_id] || ''
              const score   = scores[lead.place_id]
              const isScoring = scoringId === lead.place_id

              return (
                <div key={lead.place_id} className={`lead-card ${status}`}>

                  {/* Top row */}
                  <div className="lead-top">
                    <div className="lead-name-row">
                      <h3 className="lead-name">{lead.name}</h3>
                      {!lead.has_website && <span className="badge no-site">NO SITE</span>}
                    </div>
                    <div
                      className="status-pill"
                      style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}40` }}
                    >
                      {cfg.label}
                    </div>
                  </div>

                  {/* Info */}
                  <div className="lead-info">
                    {lead.phone && (
                      <a className="lead-phone" href={`tel:${lead.phone}`}>📞 {lead.phone}</a>
                    )}
                    {lead.website && (
                      <a className="lead-website" href={lead.website} target="_blank" rel="noreferrer">
                        🌐 {lead.website.replace(/^https?:\/\/(www\.)?/, '').slice(0, 35)}
                      </a>
                    )}
                    {lead.address && <p className="lead-address">📍 {lead.address}</p>}
                    {lead.rating  && <p className="lead-rating">⭐ {lead.rating} ({lead.total_reviews} reviews)</p>}
                  </div>

                  {/* Score section */}
                  {lead.has_website && (
                    <div className="score-section">
                      {isScoring && (
                        <div className="score-loading">
                          <span className="spinner" /> Analysing website...
                        </div>
                      )}
                      {!score && !isScoring && (
                        <div className="score-pending">⏳ Queued for analysis</div>
                      )}
                      {score && !score.error && (() => {
                        const scoreColor = score.combined_score >= 7
                          ? '#c8f135' : score.combined_score >= 4
                          ? '#ff9f43' : '#ff4d4d'
                        return (
                          <div className="score-result">
                            <div className="score-header">
                              <div className="score-badge" style={{ color: scoreColor, borderColor: scoreColor }}>
                                {score.combined_score}/10
                              </div>
                              <div className="score-meta">
                                <span>Tech: {score.technical_score}/10</span>
                                <span>Visual: {score.visual_score}/10</span>
                                <span>{score.ssl ? '🔒 SSL' : '⚠ No SSL'}</span>
                                <span>{score.mobile_responsive ? '📱 Mobile OK' : '📵 Not Mobile'}</span>
                              </div>
                            </div>
                            {score.ai_summary && (
                              <p className="score-summary">"{score.ai_summary}"</p>
                            )}
                            {score.issues?.length > 0 && (
                              <ul className="score-issues">
                                {score.issues.map((issue, i) => <li key={i}>⚠ {issue}</li>)}
                              </ul>
                            )}
                            {score.screenshot_base64 && (
                              <img
                                className="score-screenshot"
                                src={`data:image/png;base64,${score.screenshot_base64}`}
                                alt="Website screenshot"
                              />
                            )}
                          </div>
                        )
                      })()}
                      {score?.error && (
                        <div className="score-error">⚠ {score.error}</div>
                      )}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="lead-actions">
                    {(['interested', 'not_interested', 'callback', 'uncalled'] as CallStatus[]).map(s => (
                      <button
                        key={s}
                        className={`action-btn ${status === s ? 'active' : ''}`}
                        style={status === s
                          ? { background: STATUS_CONFIG[s].bg, color: STATUS_CONFIG[s].color, borderColor: STATUS_CONFIG[s].color }
                          : {}}
                        onClick={() => setStatus(lead.place_id, s)}
                      >
                        {STATUS_CONFIG[s].label}
                      </button>
                    ))}
                  </div>

                  {/* Notes */}
                  <div className="lead-notes">
                    {editingNote === lead.place_id ? (
                      <textarea
                        autoFocus
                        className="note-input"
                        value={note}
                        placeholder="Add notes..."
                        onChange={e => setNotes(prev => ({ ...prev, [lead.place_id]: e.target.value }))}
                        onBlur={() => setEditingNote(null)}
                      />
                    ) : (
                      <div className="note-display" onClick={() => setEditingNote(lead.place_id)}>
                        {note || <span className="note-placeholder">+ add note</span>}
                      </div>
                    )}
                  </div>

                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}