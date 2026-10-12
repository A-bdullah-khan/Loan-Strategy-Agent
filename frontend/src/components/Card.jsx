import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Generic financial UI card used across Home and Profile pages.
 * @param {{ title?: string, className?: string, children: React.ReactNode }} props
 */
function Card({ title, className, children }) {
  return (
    <div
      className={twMerge(
        clsx(
          'rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md',
          className,
        ),
      )}
    >
      {title ? <h3 className="mb-2 text-lg font-semibold text-navy">{title}</h3> : null}
      {children}
    </div>
  )
}

export default Card
