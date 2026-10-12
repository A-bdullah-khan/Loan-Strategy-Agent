function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="mt-auto bg-navy text-slate-300">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-6 py-6 text-sm sm:flex-row">
        <p>&copy; {year} Loan Strategy Agent. All rights reserved.</p>
        <p className="text-slate-400">Built for smarter, data-driven lending decisions.</p>
      </div>
    </footer>
  )
}

export default Footer
