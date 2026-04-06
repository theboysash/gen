import { useState } from 'react'
import { supabase } from '../supabase'

export default function Login() {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  const handleLogin = async () => {
    setLoading(true)
    setError('')
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) setError(error.message)
    setLoading(false)
  }

  return (
    <div className="login-wrap">
      <div className="login-box">
        <div className="logo">
          <span className="logo-bracket">[</span>
          LEADGEN
          <span className="logo-bracket">]</span>
        </div>
        <p className="login-sub">Sign in to your account</p>

        {error && <div className="error-msg">⚠ {error}</div>}

        <div className="login-fields">
          <div className="select-group">
            <label>EMAIL</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="login-input"
            />
          </div>
          <div className="select-group">
            <label>PASSWORD</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              className="login-input"
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
            />
          </div>
          <button
            className="generate-btn"
            onClick={handleLogin}
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center' }}
          >
            {loading ? <span className="spinner" /> : 'SIGN IN'}
          </button>
        </div>
      </div>
    </div>
  )
}