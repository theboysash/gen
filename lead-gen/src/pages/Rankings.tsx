import { useState, useEffect, useMemo } from 'react'
import { supabase } from '../supabase'

interface RankedLead {
  id: string
  place_id: string
  name: string
  address: string
  phone: string
  website: string
  has_website: boolean
  rating: number | null
  total_reviews: number | null
  industry: string
  suburb: string
  // Score fields (null if no score yet)
  combined_score: number | null
  technical_score: number | null
  visual_score: number | null
  ai_summary: string | null
  needs_revamp: boolean | null
  ssl: boolean | null
  mobile_responsive: boolean | null
  issues: string[] | null
}

type SortField = 'rank' | 'combined_score' | 'technical_score' | 'visual_score' | 'rating' | 'name'
type SortDir = 'asc' | 'desc'

export default function Rankings() {
  const [leads, setLeads]               = useState<RankedLead[]>([])
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState('')
  const [industryFilter, setIndustryFilter] = useState('')
  const [suburbFilter, setSuburbFilter] = useState('')
  const [websiteFilter, setWebsiteFilter] = useState<'all' | 'no_website' | 'has_website'>('all')
  const [revampFilter, setRevampFilter] = useState<'all' | 'needs_revamp' | 'good'>('all')
  const [sortField, setSortField]       = useState<SortField>('rank')
  const [sortDir, setSortDir]           = useState<SortDir>('asc')
  const [expandedId, setExpandedId]     = useState<string | null>(null)

  // ── Load all leads with scores ──────────────────────────
  useEffect(() => {
    loadLeads()
  }, [])

  const loadLeads = async () => {
    setLoading(true)
    setError('')

    try {
      // Fetch all leads
      const { data: leadsData, error: leadsErr } = await supabase
        .from('leads')
        .select('*')
        .order('created_at', { ascending: false })

      if (leadsErr) throw leadsErr

      // Fetch all scores
      const leadIds = (leadsData || []).map((l: any) => l.id)
      let scoresMap: Record<string, any> = {}

      if (leadIds.length > 0) {
        // Supabase .in() has a limit, batch if needed
        const batchSize = 500
        for (let i = 0; i < leadIds.length; i += batchSize) {
          const batch = leadIds.slice(i, i + batchSize)
          const { data: scoresData } = await supabase
            .from('scores')
            .select('*')
            .in('lead_id', batch)

          scoresData?.forEach((s: any) => {
            scoresMap[s.lead_id] = s
          })
        }
      }

      // Merge
      const merged: RankedLead[] = (leadsData || []).map((lead: any) => {
        const score = scoresMap[lead.id]
        return {
          id:               lead.id,
          place_id:         lead.place_id,
          name:             lead.name,
          address:          lead.address || '',
          phone:            lead.phone || '',
          website:          lead.website || '',
          has_website:      lead.has_website,
          rating:           lead.rating,
          total_reviews:    lead.total_reviews,
          industry:         lead.industry || 'Unknown',
          suburb:           lead.suburb || 'Unknown',
          combined_score:   score?.combined_score ?? null,
          technical_score:  score?.technical_score ?? null,
          visual_score:     score?.visual_score ?? null,
          ai_summary:       score?.ai_summary ?? null,
          needs_revamp:     score?.needs_revamp ?? null,
          ssl:              score?.ssl ?? null,
          mobile_responsive: score?.mobile_responsive ?? null,
          issues:           score?.issues ?? null,
        }
      })

      setLeads(merged)
    } catch (e: any) {
      console.error('Failed to load rankings:', e)
      setError(e.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  // ── Derived filter options ──────────────────────────────
  const industries = useMemo(() =>
    [...new Set(leads.map(l => l.industry))].sort(),
    [leads]
  )
  const suburbs = useMemo(() =>
    [...new Set(leads.map(l => l.suburb))].sort(),
    [leads]
  )

  // ── Filtered + sorted leads ─────────────────────────────
  const rankedLeads = useMemo(() => {
    let filtered = [...leads]

    if (industryFilter)   filtered = filtered.filter(l => l.industry === industryFilter)
    if (suburbFilter)     filtered = filtered.filter(l => l.suburb === suburbFilter)
    if (websiteFilter === 'no_website')  filtered = filtered.filter(l => !l.has_website)
    if (websiteFilter === 'has_website') filtered = filtered.filter(l => l.has_website)
    if (revampFilter === 'needs_revamp') filtered = filtered.filter(l => l.needs_revamp === true)
    if (revampFilter === 'good')         filtered = filtered.filter(l => l.needs_revamp === false)

    // Default ranking: no website first, then lowest score first (best prospects)
    if (sortField === 'rank') {
      filtered.sort((a, b) => {
        // No website always top
        if (!a.has_website && b.has_website) return -1
        if (a.has_website && !b.has_website) return 1
        // Then by combined score ascending (worst sites = best prospects)
        const scoreA = a.combined_score ?? 99
        const scoreB = b.combined_score ?? 99
        return sortDir === 'asc' ? scoreA - scoreB : scoreB - scoreA
      })
    } else {
      filtered.sort((a, b) => {
        let valA: any, valB: any
        switch (sortField) {
          case 'combined_score':  valA = a.combined_score ?? -1;  valB = b.combined_score ?? -1; break
          case 'technical_score': valA = a.technical_score ?? -1; valB = b.technical_score ?? -1; break
          case 'visual_score':    valA = a.visual_score ?? -1;    valB = b.visual_score ?? -1; break
          case 'rating':          valA = a.rating ?? -1;          valB = b.rating ?? -1; break
          case 'name':            valA = a.name.toLowerCase();    valB = b.name.toLowerCase(); break
          default:                valA = 0; valB = 0;
        }
        if (valA < valB) return sortDir === 'asc' ? -1 : 1
        if (valA > valB) return sortDir === 'asc' ? 1 : -1
        return 0
      })
    }

    return filtered
  }, [leads, industryFilter, suburbFilter, websiteFilter, revampFilter, sortField, sortDir])

  // ── Stats ───────────────────────────────────────────────
  const stats = useMemo(() => {
    const scored = rankedLeads.filter(l => l.combined_score !== null)
    const avgScore = scored.length > 0
      ? (scored.reduce((sum, l) => sum + (l.combined_score || 0), 0) / scored.length).toFixed(1)
      : '–'
    return {
      total:       rankedLeads.length,
      noWebsite:   rankedLeads.filter(l => !l.has_website).length,
      needsRevamp: rankedLeads.filter(l => l.needs_revamp).length,
      avgScore,
    }
  }, [rankedLeads])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir(field === 'name' ? 'asc' : 'desc')
    }
  }

  const sortArrow = (field: SortField) => {
    if (sortField !== field) return ''
    return sortDir === 'asc' ? ' ▲' : ' ▼'
  }

  const scoreColor = (score: number | null) => {
    if (score === null) return '#666'
    if (score >= 7) return '#c8f135'
    if (score >= 4) return '#ff9f43'
    return '#ff4d4d'
  }

  // ── Render ──────────────────────────────────────────────
  if (loading) return (
    <div className="loading-state" style={{ padding: '60px 0' }}>
      <div className="loading-dots"><span /><span /><span /></div>
      <p>Loading rankings...</p>
    </div>
  )

  if (error) return (
    <div className="error-msg" style={{ margin: 24 }}>⚠ {error}</div>
  )

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}>

      {/* Stats bar */}
      <div className="stats-bar" style={{ marginBottom: 20 }}>
        <div className="stat">
          <span className="stat-num">{stats.total}</span>
          <span className="stat-label">Showing</span>
        </div>
        <div className="stat accent">
          <span className="stat-num">{stats.noWebsite}</span>
          <span className="stat-label">No Website</span>
        </div>
        <div className="stat" style={{ color: '#ff4d4d' }}>
          <span className="stat-num">{stats.needsRevamp}</span>
          <span className="stat-label">Needs Revamp</span>
        </div>
        <div className="stat">
          <span className="stat-num">{stats.avgScore}</span>
          <span className="stat-label">Avg Score</span>
        </div>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 20,
        padding: '16px 20px', background: 'rgba(255,255,255,0.03)',
        borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)',
      }}>
        <div className="select-group" style={{ minWidth: 160 }}>
          <label>INDUSTRY</label>
          <select value={industryFilter} onChange={e => setIndustryFilter(e.target.value)}>
            <option value="">All industries</option>
            {industries.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>
        <div className="select-group" style={{ minWidth: 140 }}>
          <label>SUBURB</label>
          <select value={suburbFilter} onChange={e => setSuburbFilter(e.target.value)}>
            <option value="">All suburbs</option>
            {suburbs.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="select-group" style={{ minWidth: 140 }}>
          <label>WEBSITE</label>
          <select value={websiteFilter} onChange={e => setWebsiteFilter(e.target.value as any)}>
            <option value="all">All</option>
            <option value="no_website">No Website</option>
            <option value="has_website">Has Website</option>
          </select>
        </div>
        <div className="select-group" style={{ minWidth: 140 }}>
          <label>QUALITY</label>
          <select value={revampFilter} onChange={e => setRevampFilter(e.target.value as any)}>
            <option value="all">All</option>
            <option value="needs_revamp">Needs Revamp</option>
            <option value="good">Decent Site</option>
          </select>
        </div>
        <button
          className="action-btn"
          style={{ alignSelf: 'flex-end', marginLeft: 'auto', padding: '8px 16px' }}
          onClick={() => {
            setIndustryFilter('')
            setSuburbFilter('')
            setWebsiteFilter('all')
            setRevampFilter('all')
            setSortField('rank')
            setSortDir('asc')
          }}
        >
          Reset filters
        </button>
      </div>

      {rankedLeads.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#666' }}>
          <p style={{ fontSize: 18 }}>No leads found matching your filters.</p>
          <p style={{ fontSize: 14, marginTop: 8 }}>Try adjusting the filters above, or generate some leads first.</p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{
            width: '100%', borderCollapse: 'collapse', fontSize: 14,
          }}>
            <thead>
              <tr style={{ borderBottom: '2px solid rgba(255,255,255,0.1)' }}>
                <th style={thStyle}>#</th>
                <th style={{ ...thStyle, textAlign: 'left', cursor: 'pointer' }} onClick={() => toggleSort('name')}>
                  Business{sortArrow('name')}
                </th>
                <th style={thStyle}>Website</th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('combined_score')}>
                  Score{sortArrow('combined_score')}
                </th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('technical_score')}>
                  Tech{sortArrow('technical_score')}
                </th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('visual_score')}>
                  Visual{sortArrow('visual_score')}
                </th>
                <th style={thStyle}>SSL</th>
                <th style={thStyle}>Mobile</th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('rating')}>
                  Rating{sortArrow('rating')}
                </th>
                <th style={{ ...thStyle, textAlign: 'left' }}>Industry</th>
                <th style={{ ...thStyle, textAlign: 'left' }}>Suburb</th>
              </tr>
            </thead>
            <tbody>
              {rankedLeads.map((lead, idx) => {
                const isExpanded = expandedId === lead.id
                return (
                  <tr key={lead.id} style={{ cursor: 'default' }}>
                    {/* Rank */}
                    <td style={{ ...tdStyle, color: '#666', width: 40, textAlign: 'center' }}>
                      {idx + 1}
                    </td>

                    {/* Business name + expandable detail */}
                    <td style={{ ...tdStyle, textAlign: 'left', maxWidth: 280 }}>
                      <div>
                        <span
                          style={{ fontWeight: 600, color: '#e0e0e0', cursor: 'pointer' }}
                          onClick={() => setExpandedId(isExpanded ? null : lead.id)}
                          title="Click to expand"
                        >
                          {lead.name}
                        </span>
                        {!lead.has_website && (
                          <span style={{
                            display: 'inline-block', marginLeft: 8,
                            padding: '1px 6px', fontSize: 10, fontWeight: 700,
                            background: 'rgba(200,241,53,0.15)', color: '#c8f135',
                            borderRadius: 4, verticalAlign: 'middle',
                          }}>
                            NO SITE
                          </span>
                        )}
                        {lead.needs_revamp && (
                          <span style={{
                            display: 'inline-block', marginLeft: 6,
                            padding: '1px 6px', fontSize: 10, fontWeight: 700,
                            background: 'rgba(255,77,77,0.15)', color: '#ff4d4d',
                            borderRadius: 4, verticalAlign: 'middle',
                          }}>
                            REVAMP
                          </span>
                        )}
                      </div>
                      {lead.phone && (
                        <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>
                          <a href={`tel:${lead.phone}`} style={{ color: '#888', textDecoration: 'none' }}>
                            📞 {lead.phone}
                          </a>
                        </div>
                      )}
                      {isExpanded && (
                        <div style={{
                          marginTop: 8, padding: 12, fontSize: 12,
                          background: 'rgba(255,255,255,0.03)', borderRadius: 8,
                          border: '1px solid rgba(255,255,255,0.06)',
                        }}>
                          {lead.address && <p style={{ margin: '0 0 4px', color: '#999' }}>📍 {lead.address}</p>}
                          {lead.ai_summary && (
                            <p style={{ margin: '4px 0', color: '#ccc', fontStyle: 'italic' }}>
                              "{lead.ai_summary}"
                            </p>
                          )}
                          {lead.issues && lead.issues.length > 0 && (
                            <div style={{ marginTop: 6 }}>
                              {lead.issues.map((issue, i) => (
                                <div key={i} style={{ color: '#ff9f43', margin: '2px 0' }}>⚠ {issue}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Website */}
                    <td style={{ ...tdStyle, maxWidth: 180 }}>
                      {lead.website ? (
                        <a
                          href={lead.website}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: '#7eb8da', textDecoration: 'none', fontSize: 12 }}
                        >
                          {lead.website.replace(/^https?:\/\/(www\.)?/, '').slice(0, 28)}
                        </a>
                      ) : (
                        <span style={{ color: '#555' }}>—</span>
                      )}
                    </td>

                    {/* Combined score */}
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {lead.combined_score !== null ? (
                        <span style={{
                          display: 'inline-block', padding: '2px 10px',
                          fontWeight: 700, fontSize: 15,
                          color: scoreColor(lead.combined_score),
                          border: `1px solid ${scoreColor(lead.combined_score)}40`,
                          borderRadius: 6,
                        }}>
                          {lead.combined_score}
                        </span>
                      ) : (
                        <span style={{ color: '#555' }}>—</span>
                      )}
                    </td>

                    {/* Tech score */}
                    <td style={{ ...tdStyle, textAlign: 'center', color: scoreColor(lead.technical_score) }}>
                      {lead.technical_score !== null ? lead.technical_score : '—'}
                    </td>

                    {/* Visual score */}
                    <td style={{ ...tdStyle, textAlign: 'center', color: scoreColor(lead.visual_score) }}>
                      {lead.visual_score !== null ? lead.visual_score : '—'}
                    </td>

                    {/* SSL */}
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {lead.ssl === null ? '—' : lead.ssl ? '🔒' : '⚠'}
                    </td>

                    {/* Mobile */}
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {lead.mobile_responsive === null ? '—' : lead.mobile_responsive ? '📱' : '📵'}
                    </td>

                    {/* Google rating */}
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {lead.rating ? (
                        <span>
                          ⭐ {lead.rating}
                          <span style={{ color: '#666', fontSize: 11, marginLeft: 2 }}>
                            ({lead.total_reviews})
                          </span>
                        </span>
                      ) : (
                        <span style={{ color: '#555' }}>—</span>
                      )}
                    </td>

                    {/* Industry */}
                    <td style={{ ...tdStyle, textAlign: 'left', color: '#999', fontSize: 12 }}>
                      {lead.industry}
                    </td>

                    {/* Suburb */}
                    <td style={{ ...tdStyle, textAlign: 'left', color: '#999', fontSize: 12 }}>
                      {lead.suburb}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const thStyle: React.CSSProperties = {
  padding: '10px 12px',
  textAlign: 'center',
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: '#888',
  whiteSpace: 'nowrap',
  userSelect: 'none',
}

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
  borderBottom: '1px solid rgba(255,255,255,0.05)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}