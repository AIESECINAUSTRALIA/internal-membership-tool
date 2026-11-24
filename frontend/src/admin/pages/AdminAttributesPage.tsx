import {
  Box,
  Button,
  Chip,
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
import { useReferenceData } from '../../api/ReferenceDataContext'
import type { AttributeAppliesTo, CatalogAttribute } from '../../api/types'
import { useAuth } from '../../auth/authContext'
import { can } from '../../auth/permissions'
import { OptionToggleGroup, type ToggleOption } from '../../components/OptionToggleGroup'
import { APPLIES_TO_LABELS, DATA_TYPE_LABELS } from '../../lib/labels'
import { AttributeFormDialog, SetAttributeActiveDialog } from '../AttributeDialogs'

type Filter = 'all' | AttributeAppliesTo

const FILTERS: ToggleOption<Filter>[] = [
  { value: 'all', label: 'All' },
  { value: 'kpi', label: 'KPIs' },
  { value: 'person', label: 'Person fields' },
  { value: 'membership', label: 'Membership fields' },
]

type AttributeAction = 'add' | 'edit' | 'deactivate' | 'reactivate'

/** The dialog that is open: an action, plus the attribute it applies to (none for "add"). */
interface OpenDialog {
  action: AttributeAction
  attribute: CatalogAttribute | null
}

/** The per-row "..." menu. There is no delete: deactivating is the soft delete. */
function AttributeActionsMenu({
  attribute,
  onChoose,
}: {
  attribute: CatalogAttribute
  onChoose: (action: AttributeAction) => void
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: AttributeAction) => {
    setAnchor(null)
    onChoose(action)
  }

  return (
    <>
      <IconButton
        aria-label={`Actions for ${attribute.label}`}
        aria-haspopup="menu"
        onClick={(e) => setAnchor(e.currentTarget)}
      >
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('edit')}>Edit</MenuItem>
        {attribute.active ? (
          <MenuItem onClick={() => choose('deactivate')}>Deactivate</MenuItem>
        ) : (
          <MenuItem onClick={() => choose('reactivate')}>Reactivate</MenuItem>
        )}
      </Menu>
    </>
  )
}

/**
 * The Metrics & custom fields screen (spec §1.5, §4.2): every KPI and every custom field
 * is a row in the one `attribute` catalog, so they share one screen with a filter rather
 * than two screens. Adding a metric is a new row here, never a code or schema change.
 * Actions are only offered to people holding `manage` on `attribute`; the server checks again.
 */
export function AdminAttributesPage() {
  const api = useApi()
  const { me } = useAuth()
  const { reference } = useReferenceData()
  const [attributes, setAttributes] = useState<CatalogAttribute[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [dialog, setDialog] = useState<OpenDialog | null>(null)
  const canManage = me !== null && can(me.permissions, 'attribute', 'manage')

  const load = useCallback(() => {
    api.listAttributes().then(setAttributes)
  }, [api])

  useEffect(() => {
    load()
  }, [load])

  const functionLabel = (key: string | null) =>
    key === null ? 'All functions' : (reference?.functions.find((f) => f.key === key)?.label ?? key)
  const shown = filter === 'all' ? attributes : attributes.filter((a) => a.appliesTo === filter)
  const closeDialog = () => setDialog(null)

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
        <Box>
          <Typography id="attributes-title" variant="h1" component="h1">
            Metrics & custom fields
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
            The KPIs people track, and the extra fields kept about people and memberships. Deactivating one never
            deletes what was already recorded.
          </Typography>
        </Box>
        {canManage && (
          <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setDialog({ action: 'add', attribute: null })}>
            Add
          </Button>
        )}
      </Stack>
      <Paper variant="outlined" component="section" aria-labelledby="attributes-title" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Box>
            <OptionToggleGroup value={filter} options={FILTERS} onChange={setFilter} ariaLabel="Show" />
          </Box>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" aria-labelledby="attributes-title">
              <TableHead>
                <TableRow>
                  <TableCell>Label</TableCell>
                  <TableCell>Key</TableCell>
                  <TableCell>Applies to</TableCell>
                  <TableCell>Data type</TableCell>
                  <TableCell>Function</TableCell>
                  <TableCell>Status</TableCell>
                  {canManage && <TableCell aria-label="Actions" />}
                </TableRow>
              </TableHead>
              <TableBody>
                {shown.map((attribute) => (
                  <TableRow key={attribute.id}>
                    <TableCell>{attribute.label}</TableCell>
                    <TableCell>
                      <Box component="code">{attribute.key}</Box>
                    </TableCell>
                    <TableCell>{APPLIES_TO_LABELS[attribute.appliesTo]}</TableCell>
                    <TableCell>
                      {DATA_TYPE_LABELS[attribute.dataType]}
                      {attribute.unit && ` (${attribute.unit})`}
                    </TableCell>
                    <TableCell>{functionLabel(attribute.functionKey)}</TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label={attribute.active ? 'Active' : 'Inactive'} />
                    </TableCell>
                    {canManage && (
                      <TableCell align="right">
                        <AttributeActionsMenu attribute={attribute} onChoose={(action) => setDialog({ action, attribute })} />
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
          {shown.length === 0 && <Typography color="text.secondary">Nothing here yet.</Typography>}
        </Stack>
      </Paper>

      {dialog?.action === 'add' && <AttributeFormDialog attribute={null} onClose={closeDialog} onDone={load} />}
      {dialog?.attribute && dialog.action === 'edit' && (
        <AttributeFormDialog attribute={dialog.attribute} onClose={closeDialog} onDone={load} />
      )}
      {dialog?.attribute && (dialog.action === 'deactivate' || dialog.action === 'reactivate') && (
        <SetAttributeActiveDialog
          attribute={dialog.attribute}
          makeActive={dialog.action === 'reactivate'}
          onClose={closeDialog}
          onDone={load}
        />
      )}
    </Stack>
  )
}
