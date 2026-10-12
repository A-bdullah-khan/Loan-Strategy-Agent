// The chat agent's `update_loan_state` tool stores loan_type exactly as
// "Personal" / "Home" / "Vehicle" (see backend mcp_server/agent.py) — not
// the lowercase users.models.LoanRequestType values, which only exist once
// a LoanRequest row is created server-side.
export const LOAN_TYPE_LABELS = {
  Personal: 'Personal Loan',
  Home: 'Home Loan',
  Vehicle: 'Vehicle Loan',
}

/**
 * @param {number | null | undefined} amount
 * @returns {string}
 */
export function formatPkr(amount) {
  if (amount === null || amount === undefined) return '—'
  return `PKR ${Number(amount).toLocaleString()}`
}
