import { useEffect, useState } from 'react'
import { UserCircle } from 'lucide-react'
import Card from '../components/Card'
import { getProfile } from '../services/profile'

function Profile() {
  const [profile, setProfile] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let isMounted = true

    getProfile()
      .then((response) => {
        if (isMounted) setProfile(response.data)
      })
      .catch(() => {
        if (isMounted) setError('Unable to load your profile right now.')
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [])

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-3xl font-bold text-navy">Profile</h1>

      {isLoading ? <p className="mt-8 text-slate-500">Loading profile...</p> : null}
      {error ? <p className="mt-8 text-red-600">{error}</p> : null}

      {!isLoading && !error && profile ? (
        <Card className="mt-8 flex items-start gap-4">
          <UserCircle className="h-12 w-12 text-navy" />
          <div>
            <p className="text-lg font-semibold text-navy">{profile.fullName}</p>
            <p className="text-sm text-slate-600">{profile.email}</p>
          </div>
        </Card>
      ) : null}

      {!isLoading && !error && !profile ? (
        <p className="mt-8 text-slate-500">No profile information available yet.</p>
      ) : null}
    </div>
  )
}

export default Profile
