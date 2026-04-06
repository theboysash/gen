import { useEffect, useState } from 'react'
import { supabase } from '../supabase'

interface SavedLead {
  id: string
  created_at: string
  lead_id: string
  user_id: string
  leads: {
    name: string
    address: string
    phone: string
    website: string
    industry: string
    suburb: string
    rating: number
    total_reviews: number
  }
  profiles: {
    name: string
    email: string
  }
  scores: {
    combined_score: number
    ai_summary: string
    screenshot_url: string
    needs_revamp: boolean
  } | null
}

export default function SavedLeads({ isAdmin }: { isAdmin: boolean }) {
  const [savedLeads, setSavedLeads] = useState<SavedLead[]>([])
  const [loading, setLoading]       = useState(true)

  useEffect(() => {
    fetchSaved()
  }, [])

  const fetchSaved = async () => {
    setLoading(true)

    let query = supabase
      .from('liked_leads')
      .select(`
        *,
        leads (
          name, address, phone, website,
          industry, suburb, rating, total_reviews
        ),
        profiles (
          name, email
        ),
        scores:scores!inner (
          combined_score, ai_summary, screenshot_url, needs_revamp
        )
      `)
      .order('created_at', { ascending: false })

    // If not admin only show own liked leads
    if (!isAdmin) {
      const { data: { user } } = await supabase.auth.getUser()
      if (user) query = query.eq('user_id', user.id)
    }

    const { data, error } = await query
    if (error) console.error(error)
    else setSavedLeads(data || [])
    setLoading(false)
  }

  const unlike = async (id: string) => {
    await supabase.from('liked_leads').delete().eq('id', id)
    setSavedLeads(prev => prev.filter(l => l.id !== id))
  }

  if (loading) return (
    <div className="loading-state">
      <div className="loading-dots"><span /><span /><span /></div>
      <p>Loading saved leads...</p>
    </div>
  )

  return (
    <div className="app">
      <div className="results-header" style={{ marginBottom: 24 }}>
        <span>Saved Leads {isAdmin ? '(All Team)' : '(Mine)'}</span>
        <span className="results-hint">{savedLeads.length} total</span>
      </div>

      {savedLeads.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No saved leads yet.</p>
      )}

      <div className="leads-grid">
        {savedLeads.map(sl => {
          const lead  = sl.leads
          const score = sl.scores
          const scoreColor = score
            ? score.combined_score >= 7 ? '#c8f135'
            : score.combined_score >= 4 ? '#ff9f43' : '#ff4d4d'
            : '#666'

          return (
            <div key={sl.id} className="lead-card">
              <div className="lead-top">
                <div className="lead-name-row">
                  <h3 className="lead-name">{lead.name}</h3>
                  {!lead.website && <span className="badge no-site">NO SITE</span>}
                </div>
                {isAdmin && (
                  <span style={{ fontSize: 10, color: 'var(--accent)', letterSpacing: 1 }}>
                    {sl.profiles.name}
                  </span>
                )}
              </div>

              <div className="lead-info">
                {lead.phone && <a className="lead-phone" href={`tel:${lead.phone}`}>📞 {lead.phone}</a>}
                {lead.website && (
                  <a className="lead-website" href={lead.website} target="_blank" rel="noreferrer">
                    🌐 {lead.website.replace(/^https?:\/\/(www\.)?/, '').slice(0, 35)}
                  </a>
                )}
                {lead.address && <p className="lead-address">📍 {lead.address}</p>}
                {lead.rating && <p className="lead-rating">⭐ {lead.rating} ({lead.total_reviews} reviews)</p>}
                <p className="lead-address">🏷 {lead.industry} · {lead.suburb}</p>
              </div>

              {score && (
                <div className="score-result">
                  <div className="score-header">
                    <div className="score-badge" style={{ color: scoreColor, borderColor: scoreColor }}>
                      {score.combined_score}/10
                    </div>
                  </div>
                  {score.ai_summary && <p className="score-summary">"{score.ai_summary}"</p>}
                  {score.screenshot_url && (
                    <img className="score-screenshot" src={score.screenshot_url} alt="screenshot" />
                  )}
                </div>
              )}

              <button
                className="score-btn"
                onClick={() => unlike(sl.id)}
                style={{ marginTop: 8 }}
              >
                ♥ Remove from saved
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}