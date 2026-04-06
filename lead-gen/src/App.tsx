import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { supabase } from './supabase'
import Login from './auth/Login'
import SavedLeads from './pages/SavedLeads'
import Rankings from './pages/Rankings'
import './App.css'

const GOOGLE_API_KEY = import.meta.env.VITE_GOOGLE_API_KEY
const SCORE_API      = import.meta.env.VITE_SCORE_API || 'http://localhost:5000'

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
  id?: string
  place_id: string
  name: string
  address: string
  phone: string
  website: string
  has_website: boolean
  rating: number | null
  total_reviews: number | null
  industry?: string
  suburb?: string
}

interface ScoreResult {
  screenshot_url: string
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

interface Profile {
  id: string
  name: string
  email: string
  role: 'admin' | 'staff'
}

type CallStatus = 'uncalled' | 'interested' | 'not_interested' | 'callback'
type Page = 'leads' | 'saved' | 'rankings'

const STATUS_CONFIG = {
  uncalled:       { label: 'Not Called',     color: '#666',    bg: 'rgba(100,100,100,0.1)' },
  interested:     { label: 'Interested',     color: '#c8f135', bg: 'rgba(200,241,53,0.1)'  },
  not_interested: { label: 'Not Interested', color: '#ff4d4d', bg: 'rgba(255,77,77,0.1)'   },
  callback:       { label: 'Call Back',      color: '#ff9f43', bg: 'rgba(255,159,67,0.1)'  },
}

// ── Unique ID for each scoring run to prevent races ────
let scoringRunId = 0

export default function App() {
  const [profile, setProfile]           = useState<Profile | null>(null)
  const [authLoading, setAuthLoading]   = useState(true)
  const [page, setPage]                 = useState<Page>('leads')
  const [industry, setIndustry]         = useState('')
  const [suburb, setSuburb]             = useState('')
  const [leads, setLeads]               = useState<Lead[]>([])
  const [loading, setLoading]           = useState(false)
  const [loadingMsg, setLoadingMsg]     = useState('')
  const [error, setError]               = useState('')
  const [statuses, setStatuses]         = useState<Record<string, CallStatus>>({})
  const [notes, setNotes]               = useState<Record<string, string>>({})
  const [editingNote, setEditingNote]   = useState<string | null>(null)
  const [scores, setScores]             = useState<Record<string, ScoreResult>>({})
  const [scoringIds, setScoringIds]     = useState<Set<string>>(new Set())
  const [scoringProgress, setScoringProgress] = useState({ done: 0, total: 0 })
  const [likedLeads, setLikedLeads]     = useState<Set<string>>(new Set())
  const [imgErrors, setImgErrors]       = useState<Set<string>>(new Set())

  // ── Auth ────────────────────────────────────────────────
  useEffect(() => {
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.user) await loadProfile(session.user.id)
      setAuthLoading(false)
    }).catch(() => setAuthLoading(false))

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (session?.user) await loadProfile(session.user.id)
      else setProfile(null)
    })
    return () => subscription.unsubscribe()
  }, [])

  const loadProfile = async (userId: string) => {
    const { data } = await supabase.from('profiles').select('*').eq('id', userId).single()
    if (data) setProfile(data)
  }

  const signOut = async () => {
    await supabase.auth.signOut()
    setProfile(null)
    setLeads([])
    setScores({})
    setStatuses({})
  }

  // ── Load liked leads ────────────────────────────────────
  useEffect(() => {
    if (!profile) return
    supabase
      .from('liked_leads')
      .select('lead_id')
      .eq('user_id', profile.id)
      .then(({ data }) => {
        if (data) setLikedLeads(new Set(data.map((l: any) => l.lead_id)))
      })
  }, [profile])

  // ── Score a single lead ─────────────────────────────────
  const scoreSingleLead = useCallback(async (lead: Lead): Promise<ScoreResult | null> => {
    // 1. Check Supabase cache
    if (lead.id) {
      try {
        const { data: existing } = await supabase
          .from('scores')
          .select('*')
          .eq('lead_id', lead.id)
          .maybeSingle()

        if (existing) return existing as ScoreResult
      } catch (e) {
        console.warn('Cache check failed, scoring fresh:', e)
      }
    }

    // 2. Call the scoring API
    const res = await axios.get(
      `${SCORE_API}/score?url=${encodeURIComponent(lead.website)}`,
      { timeout: 45000 }
    )
    const scoreData: ScoreResult = res.data

    // 3. Save to Supabase
    if (lead.id && !scoreData.error) {
      try {
        await supabase.from('scores').upsert({
          lead_id:           lead.id,
          technical_score:   scoreData.technical_score,
          visual_score:      scoreData.visual_score,
          combined_score:    scoreData.combined_score,
          issues:            scoreData.issues,
          ai_summary:        scoreData.ai_summary,
          needs_revamp:      scoreData.needs_revamp,
          ssl:               scoreData.ssl,
          mobile_responsive: scoreData.mobile_responsive,
          screenshot_url:    scoreData.screenshot_url,
        })
      } catch (e) {
        console.warn('Failed to cache score:', e)
      }
    }

    return scoreData
  }, [])

  // ── Process scoring queue (parallel workers) ────────────
  const CONCURRENCY = 4

  const processQueue = useCallback(async (queue: Lead[], runId: number) => {
    let index = 0

    const worker = async () => {
      while (index < queue.length) {
        // Grab the next lead atomically
        const i = index++
        if (i >= queue.length) break

        // If a new run started, abandon this one
        if (scoringRunId !== runId) return

        const lead = queue[i]
        setScoringIds(prev => new Set([...prev, lead.place_id]))

        try {
          const scoreData = await scoreSingleLead(lead)
          if (scoreData) {
            setScores(prev => ({ ...prev, [lead.place_id]: scoreData }))
          }
        } catch (e) {
          console.error(`Score error for ${lead.name}:`, e)
          setScores(prev => ({
            ...prev,
            [lead.place_id]: {
              screenshot_url: '',
              technical_score: 0,
              visual_score: 0,
              combined_score: 0,
              issues: [],
              ai_summary: 'Could not analyse',
              needs_revamp: false,
              mobile_responsive: false,
              ssl: false,
              error: 'Failed to analyse',
            },
          }))
        }

        // Always advance progress and clear this lead from active set
        setScoringIds(prev => { const s = new Set(prev); s.delete(lead.place_id); return s })
        setScoringProgress(prev => ({ ...prev, done: prev.done + 1 }))
      }
    }

    // Launch N workers in parallel
    const workers = Array.from({ length: Math.min(CONCURRENCY, queue.length) }, () => worker())
    await Promise.all(workers)
  }, [scoreSingleLead])

  // ── Fetch leads ─────────────────────────────────────────
  const fetchLeads = async () => {
    if (!industry || !suburb || !profile) return
    setLoading(true)
    setError('')
    setLeads([])
    setScores({})
    setImgErrors(new Set())
    setScoringProgress({ done: 0, total: 0 })
    setScoringIds(new Set())

    // Cancel any in-progress scoring run
    scoringRunId += 1
    const thisRunId = scoringRunId

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

      allPlaces = [...(res1.data.places || [])]
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
        industry,
        suburb,
      }))

      parsed.sort((a, b) => {
        if (!a.has_website && b.has_website) return -1
        if (a.has_website && !b.has_website) return 1
        return (b.rating || 0) - (a.rating || 0)
      })

      // Bulk upsert leads
      setLoadingMsg('Saving leads...')
      const { data: upsertedData, error: upsertError } = await supabase
        .from('leads')
        .upsert(
          parsed.map(lead => ({
            place_id:      lead.place_id,
            name:          lead.name,
            address:       lead.address,
            phone:         lead.phone,
            website:       lead.website,
            has_website:   lead.has_website,
            rating:        lead.rating,
            total_reviews: lead.total_reviews,
            industry,
            suburb,
          })),
          { onConflict: 'place_id' }
        )
        .select()

      if (upsertError) {
        console.error('Upsert error:', upsertError)
        setError('Failed to save leads: ' + upsertError.message)
        return
      }

      const upserted: Lead[] = parsed.map(lead => {
        const saved = upsertedData?.find((d: any) => d.place_id === lead.place_id)
        return saved ? { ...lead, id: saved.id } : lead
      })

      // Load existing statuses and notes
      const leadIds = upserted.filter(l => l.id).map(l => l.id!)
      if (leadIds.length > 0) {
        const [statusRes, notesRes] = await Promise.all([
          supabase.from('call_statuses').select('*').eq('user_id', profile.id).in('lead_id', leadIds),
          supabase.from('notes').select('*').eq('user_id', profile.id).in('lead_id', leadIds),
        ])

        const statusMap: Record<string, CallStatus> = {}
        const noteMap: Record<string, string> = {}

        statusRes.data?.forEach((s: any) => {
          const lead = upserted.find(l => l.id === s.lead_id)
          if (lead) statusMap[lead.place_id] = s.status
        })

        notesRes.data?.forEach((n: any) => {
          const lead = upserted.find(l => l.id === n.lead_id)
          if (lead) noteMap[lead.place_id] = n.content
        })

        setStatuses(statusMap)
        setNotes(noteMap)
      }

      setLeads(upserted)

      // Start scoring queue
      const toScore = upserted.filter(l => l.has_website)
      setScoringProgress({ done: 0, total: toScore.length })

      // Fire and forget — the runId check will cancel if needed
      processQueue(toScore, thisRunId)

    } catch (e: any) {
      setError(e?.response?.data?.error?.message || 'Something went wrong')
    } finally {
      setLoading(false)
      setLoadingMsg('')
    }
  }

  // ── Status update ───────────────────────────────────────
  const setStatus = async (lead: Lead, status: CallStatus) => {
    setStatuses(prev => ({ ...prev, [lead.place_id]: status }))
    if (!lead.id || !profile) return
    await supabase.from('call_statuses').upsert({
      lead_id:    lead.id,
      user_id:    profile.id,
      status,
      updated_at: new Date().toISOString(),
    }, { onConflict: 'lead_id,user_id' })
  }

  // ── Note update ─────────────────────────────────────────
  const saveNote = async (lead: Lead, content: string) => {
    setNotes(prev => ({ ...prev, [lead.place_id]: content }))
    if (!lead.id || !profile) return
    const { data: existing } = await supabase
      .from('notes')
      .select('id')
      .eq('lead_id', lead.id)
      .eq('user_id', profile.id)
      .maybeSingle()

    if (existing) {
      await supabase.from('notes').update({ content }).eq('id', existing.id)
    } else {
      await supabase.from('notes').insert({ lead_id: lead.id, user_id: profile.id, content })
    }
  }

  // ── Like / unlike ───────────────────────────────────────
  const toggleLike = async (lead: Lead) => {
    if (!lead.id || !profile) return
    const isLiked = likedLeads.has(lead.id)
    if (isLiked) {
      await supabase.from('liked_leads').delete().eq('lead_id', lead.id).eq('user_id', profile.id)
      setLikedLeads(prev => { const s = new Set(prev); s.delete(lead.id!); return s })
    } else {
      await supabase.from('liked_leads').insert({ lead_id: lead.id, user_id: profile.id })
      setLikedLeads(prev => new Set([...prev, lead.id!]))
    }
  }

  const stats = {
    total:      leads.length,
    no_website: leads.filter(l => !l.has_website).length,
    interested: Object.values(statuses).filter(s => s === 'interested').length,
    called:     Object.values(statuses).filter(s => s !== 'uncalled').length,
  }

  const analysisComplete = scoringProgress.total > 0 &&
    scoringProgress.done === scoringProgress.total

  // ── Render guards ────────────────────────────────────────
  if (authLoading) return (
    <div className="loading-state" style={{ height: '100vh' }}>
      <div className="loading-dots"><span /><span /><span /></div>
    </div>
  )

  if (!profile) return <Login />

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-bracket">[</span>LEADGEN<span className="logo-bracket">]</span>
          </div>
          <p className="tagline">Joburg small business lead intelligence</p>
        </div>
        <div className="header-right">
          <nav className="nav">
            <button className={`nav-btn ${page === 'leads' ? 'active' : ''}`} onClick={() => setPage('leads')}>Leads</button>
            <button className={`nav-btn ${page === 'saved' ? 'active' : ''}`} onClick={() => setPage('saved')}>Saved</button>
            <button className={`nav-btn ${page === 'rankings' ? 'active' : ''}`} onClick={() => setPage('rankings')}>Rankings</button>
          </nav>
          <span className="user-pill">{profile.name} · {profile.role}</span>
          <button className="signout-btn" onClick={signOut}>Sign out</button>
        </div>
      </header>

      {page === 'saved' && <SavedLeads isAdmin={profile.role === 'admin'} />}
      {page === 'rankings' && <Rankings />}

      {page === 'leads' && (
        <>
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

            {leads.length > 0 && (
              <div className="stats-bar">
                <div className="stat"><span className="stat-num">{stats.total}</span><span className="stat-label">Total</span></div>
                <div className="stat accent"><span className="stat-num">{stats.no_website}</span><span className="stat-label">No Website</span></div>
                <div className="stat green"><span className="stat-num">{stats.interested}</span><span className="stat-label">Interested</span></div>
                <div className="stat"><span className="stat-num">{stats.called}</span><span className="stat-label">Called</span></div>
              </div>
            )}

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

          {error && <div className="error-msg">⚠ {error}</div>}

          {loading && (
            <div className="loading-state">
              <div className="loading-dots"><span /><span /><span /></div>
              <p>{loadingMsg || `Scanning ${suburb} for ${industry}...`}</p>
            </div>
          )}

          {leads.length > 0 && (
            <div className="results">
              <div className="results-header">
                <span>{leads.length} leads found in {suburb}</span>
                <span className="results-hint">Sorted: no website first</span>
              </div>

              <div className="leads-grid">
                {leads.map(lead => {
                  const status    = statuses[lead.place_id] || 'uncalled'
                  const cfg       = STATUS_CONFIG[status]
                  const note      = notes[lead.place_id] || ''
                  const score     = scores[lead.place_id]
                  const isScoring = scoringIds.has(lead.place_id)
                  const isLiked   = lead.id ? likedLeads.has(lead.id) : false

                  return (
                    <div key={lead.place_id} className={`lead-card ${status}`}>

                      {/* Top row */}
                      <div className="lead-top">
                        <div className="lead-name-row">
                          <h3 className="lead-name">{lead.name}</h3>
                          {!lead.has_website && <span className="badge no-site">NO SITE</span>}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <button
                            className="like-btn"
                            onClick={() => toggleLike(lead)}
                            style={{ color: isLiked ? '#ff4d4d' : '#444' }}
                          >
                            {isLiked ? '♥' : '♡'}
                          </button>
                          <div
                            className="status-pill"
                            style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}40` }}
                          >
                            {cfg.label}
                          </div>
                        </div>
                      </div>

                      {/* Info */}
                      <div className="lead-info">
                        {lead.phone && <a className="lead-phone" href={`tel:${lead.phone}`}>📞 {lead.phone}</a>}
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
                            <div className="score-loading"><span className="spinner" /> Analysing website...</div>
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
                                {score.screenshot_url && !imgErrors.has(lead.place_id) && (
                                  <img
                                    className="score-screenshot"
                                    src={score.screenshot_url}
                                    alt={`${lead.name} website screenshot`}
                                    loading="lazy"
                                    onError={() => {
                                      console.warn('Screenshot failed to load:', score.screenshot_url)
                                      setImgErrors(prev => new Set([...prev, lead.place_id]))
                                    }}
                                  />
                                )}
                                {imgErrors.has(lead.place_id) && (
                                  <div className="score-img-fallback">
                                    📷 Screenshot unavailable —{' '}
                                    <a href={lead.website} target="_blank" rel="noreferrer">
                                      visit site
                                    </a>
                                  </div>
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
                            onClick={() => setStatus(lead, s)}
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
                            onBlur={() => {
                              setEditingNote(null)
                              saveNote(lead, notes[lead.place_id] || '')
                            }}
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
        </>
      )}
    </div>
  )
}