import { IconButton, Menu, MenuItem } from '@mui/material'
import MoreVert from '@mui/icons-material/MoreVert'
import { useState } from 'react'

import type { MemberSummaryRow } from '../../api/types'
import type { RowActions } from '../../auth/permissions'
import { fullName } from '../../lib/labels'
import type { ManageKind } from './ManageMembershipDialog'

/**
 * The per-row "..." menu. It lists only actions this person may take on this row
 * (hierarchy rule, spec §3.4), and renders nothing when there are none.
 */
export function MemberActionsMenu({
  row,
  actions,
  onChoose,
}: {
  row: MemberSummaryRow
  actions: RowActions
  onChoose: (kind: ManageKind) => void
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  if (actions.extendRoleIds.length === 0 && actions.moveRoleIds.length === 0) return null

  const choose = (kind: ManageKind) => {
    setAnchor(null)
    onChoose(kind)
  }

  return (
    <>
      <IconButton
        aria-label={`Actions for ${fullName(row.firstName, row.lastName)}`}
        aria-haspopup="menu"
        onClick={(e) => setAnchor(e.currentTarget)}
      >
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {actions.moveRoleIds.length > 0 && <MenuItem onClick={() => choose('move')}>Move to team</MenuItem>}
        {actions.extendRoleIds.length > 0 && <MenuItem onClick={() => choose('extend')}>Extend term</MenuItem>}
      </Menu>
    </>
  )
}
