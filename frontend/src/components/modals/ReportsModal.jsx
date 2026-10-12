import ReportsView from '../ReportsView'
import Modal from './Modal'

/**
 * @param {{ isOpen: boolean, onClose: () => void }} props
 */
function ReportsModal({ isOpen, onClose }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="All Reports Audit Log">
      <ReportsView />
    </Modal>
  )
}

export default ReportsModal
