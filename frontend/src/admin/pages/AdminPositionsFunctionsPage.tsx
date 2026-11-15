import {
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import AddOutlined from '@mui/icons-material/AddOutlined'
import MoreVert from '@mui/icons-material/MoreVert'
import { useCallback, useEffect, useState } from 'react'

import { useApi } from '../../api/ApiContext'
import type { AdminFunctionRow, AdminPositionRow } from '../../api/types'
import { can } from '../../auth/permissions'
import { useAuth } from '../../auth/authContext'
import {
  AddFunctionDialog,
  AddPositionDialog,
  EditPositionDetailsDialog,
  RenameFunctionDialog,
  RenamePositionDialog,
  SetFunctionActiveDialog,
  SetPositionActiveDialog,
} from '../PositionFunctionDialogs'

// ---------------------------------------------------------------------------
// Position section
// ---------------------------------------------------------------------------

type PositionAction = 'rename' | 'edit_details' | 'set_inactive' | 'set_active'
type FunctionAction = 'rename' | 'set_inactive' | 'set_active'

interface OpenPositionDialog {
  action: PositionAction | 'add'
  position: AdminPositionRow | null
}

interface OpenFunctionDialog {
  action: FunctionAction | 'add'
  func: AdminFunctionRow | null
}

function PositionActionsMenu({
  position,
  onChoose,
}: {
  position: AdminPositionRow
  onChoose: (action: PositionAction) => void
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: PositionAction) => {
    setAnchor(null)
    onChoose(action)
  }

  return (
    <>
      <IconButton aria-label={`Actions for ${position.label}`} aria-haspopup="menu" onClick={(e) => setAnchor(e.currentTarget)}>
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('rename')}>Rename</MenuItem>
        <MenuItem onClick={() => choose('edit_details')}>Edit rank / level</MenuItem>
        {position.active && <MenuItem onClick={() => choose('set_inactive')}>Deactivate</MenuItem>}
        {!position.active && <MenuItem onClick={() => choose('set_active')}>Reactivate</MenuItem>}
      </Menu>
    </>
  )
}

function FunctionActionsMenu({
  func,
  onChoose,
}: {
  func: AdminFunctionRow
  onChoose: (action: FunctionAction) => void
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: FunctionAction) => {
    setAnchor(null)
    onChoose(action)
  }

  return (
    <>
      <IconButton aria-label={`Actions for ${func.label}`} aria-haspopup="menu" onClick={(e) => setAnchor(e.currentTarget)}>
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('rename')}>Rename</MenuItem>
        {func.active && <MenuItem onClick={() => choose('set_inactive')}>Deactivate</MenuItem>}
        {!func.active && <MenuItem onClick={() => choose('set_active')}>Reactivate</MenuItem>}
      </Menu>
    </>
  )
}

/**
 * Positions & functions screen (spec §1.5, §2A.2).
 *
 * Two sections on the same page: Positions (with rank, level and the
 * can-add-same-rank flag) and Functions (a flat list). Deactivating either does
 * not break historical memberships — it only stops that value being offered to
 * new memberships (spec §1.5). There is no delete.
 *
 * Access: `position:manage` for the whole page. `function:manage` is a subset
 * of that (all MC positions also hold it via the Settings → Functions path,
 * spec §2A.8), but the Admin console only surfaces this unified screen to anyone
 * who already has `position:manage`.
 */
export function AdminPositionsFunctionsPage() {
  const api = useApi()
  const { me } = useAuth()
  const canManagePositions = me !== null && can(me.permissions, 'position', 'manage')
  const canManageFunctions = me !== null && can(me.permissions, 'function', 'manage')

  const [positions, setPositions] = useState<AdminPositionRow[]>([])
  const [functions_, setFunctions] = useState<AdminFunctionRow[]>([])
  const [positionDialog, setPositionDialog] = useState<OpenPositionDialog | null>(null)
  const [functionDialog, setFunctionDialog] = useState<OpenFunctionDialog | null>(null)

  const loadPositions = useCallback(() => {
    api.listPositionsAdmin().then(setPositions)
  }, [api])

  const loadFunctions = useCallback(() => {
    api.listFunctionsAdmin().then(setFunctions)
  }, [api])

  useEffect(() => {
    loadPositions()
    loadFunctions()
  }, [loadPositions, loadFunctions])

  const closePositionDialog = () => setPositionDialog(null)
  const closeFunctionDialog = () => setFunctionDialog(null)

  return (
    <Stack spacing={4}>
      {/* Positions --------------------------------------------------------- */}
      <Stack spacing={3}>
        <Stack
          direction="row"
          sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}
        >
          <Box>
            <Typography id="positions-title" variant="h1" component="h1">
              Positions &amp; functions
            </Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
              Positions define a person's role and rank. Functions define their department. Both are runtime-editable
              (§1.5) — deactivating a value stops it being offered to new memberships but does not affect history.
            </Typography>
          </Box>
        </Stack>

        <Stack
          direction="row"
          sx={{ justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}
        >
          <Typography variant="h2" component="h2" id="positions-heading">
            Positions
          </Typography>
          {canManagePositions && (
            <Button
              variant="contained"
              startIcon={<AddOutlined />}
              onClick={() => setPositionDialog({ action: 'add', position: null })}
            >
              Add position
            </Button>
          )}
        </Stack>

        <Paper variant="outlined" component="section" aria-labelledby="positions-heading" sx={{ p: 3 }}>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" aria-labelledby="positions-heading">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Key</TableCell>
                  <TableCell>Level</TableCell>
                  <TableCell>Rank</TableCell>
                  <TableCell>Can add same rank</TableCell>
                  <TableCell>Status</TableCell>
                  {canManagePositions && <TableCell aria-label="Actions" />}
                </TableRow>
              </TableHead>
              <TableBody>
                {positions.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={canManagePositions ? 7 : 6} sx={{ color: 'text.secondary', py: 3, textAlign: 'center' }}>
                      No data exists
                    </TableCell>
                  </TableRow>
                ) : (
                  positions.map((position) => (
                    <TableRow key={position.id}>
                      <TableCell>{position.label}</TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace" color="text.secondary">
                          {position.key}
                        </Typography>
                      </TableCell>
                      <TableCell>{position.level ? position.level.toUpperCase() : '—'}</TableCell>
                      <TableCell>{position.rank ?? '—'}</TableCell>
                      <TableCell>{position.canAddSameRank ? 'Yes' : 'No'}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          variant="outlined"
                          label={position.active ? 'Active' : 'Inactive'}
                        />
                      </TableCell>
                      {canManagePositions && (
                        <TableCell align="right">
                          <PositionActionsMenu
                            position={position}
                            onChoose={(action) => setPositionDialog({ action, position })}
                          />
                        </TableCell>
                      )}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      </Stack>

      <Divider />

      {/* Functions --------------------------------------------------------- */}
      <Stack spacing={3}>
        <Stack
          direction="row"
          sx={{ justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}
        >
          <Typography variant="h2" component="h2" id="functions-heading">
            Functions
          </Typography>
          {canManageFunctions && (
            <Button
              variant="contained"
              startIcon={<AddOutlined />}
              onClick={() => setFunctionDialog({ action: 'add', func: null })}
            >
              Add function
            </Button>
          )}
        </Stack>

        <Paper variant="outlined" component="section" aria-labelledby="functions-heading" sx={{ p: 3 }}>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" aria-labelledby="functions-heading">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Key</TableCell>
                  <TableCell>Status</TableCell>
                  {canManageFunctions && <TableCell aria-label="Actions" />}
                </TableRow>
              </TableHead>
              <TableBody>
                {functions_.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={canManageFunctions ? 4 : 3} sx={{ color: 'text.secondary', py: 3, textAlign: 'center' }}>
                      No data exists
                    </TableCell>
                  </TableRow>
                ) : (
                  functions_.map((func) => (
                    <TableRow key={func.id}>
                      <TableCell>{func.label}</TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace" color="text.secondary">
                          {func.key}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          variant="outlined"
                          label={func.active ? 'Active' : 'Inactive'}
                        />
                      </TableCell>
                      {canManageFunctions && (
                        <TableCell align="right">
                          <FunctionActionsMenu
                            func={func}
                            onChoose={(action) => setFunctionDialog({ action, func })}
                          />
                        </TableCell>
                      )}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      </Stack>

      {/* Position dialogs */}
      {positionDialog?.action === 'add' && (
        <AddPositionDialog onClose={closePositionDialog} onDone={loadPositions} />
      )}
      {positionDialog?.position && positionDialog.action === 'rename' && (
        <RenamePositionDialog
          position={positionDialog.position}
          onClose={closePositionDialog}
          onDone={loadPositions}
        />
      )}
      {positionDialog?.position && positionDialog.action === 'edit_details' && (
        <EditPositionDetailsDialog
          position={positionDialog.position}
          onClose={closePositionDialog}
          onDone={loadPositions}
        />
      )}
      {positionDialog?.position && positionDialog.action === 'set_inactive' && (
        <SetPositionActiveDialog
          position={positionDialog.position}
          makeActive={false}
          onClose={closePositionDialog}
          onDone={loadPositions}
        />
      )}
      {positionDialog?.position && positionDialog.action === 'set_active' && (
        <SetPositionActiveDialog
          position={positionDialog.position}
          makeActive
          onClose={closePositionDialog}
          onDone={loadPositions}
        />
      )}

      {/* Function dialogs */}
      {functionDialog?.action === 'add' && (
        <AddFunctionDialog onClose={closeFunctionDialog} onDone={loadFunctions} />
      )}
      {functionDialog?.func && functionDialog.action === 'rename' && (
        <RenameFunctionDialog
          func={functionDialog.func}
          onClose={closeFunctionDialog}
          onDone={loadFunctions}
        />
      )}
      {functionDialog?.func && functionDialog.action === 'set_inactive' && (
        <SetFunctionActiveDialog
          func={functionDialog.func}
          makeActive={false}
          onClose={closeFunctionDialog}
          onDone={loadFunctions}
        />
      )}
      {functionDialog?.func && functionDialog.action === 'set_active' && (
        <SetFunctionActiveDialog
          func={functionDialog.func}
          makeActive
          onClose={closeFunctionDialog}
          onDone={loadFunctions}
        />
      )}
    </Stack>
  )
}
