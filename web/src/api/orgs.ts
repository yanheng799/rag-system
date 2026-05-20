import request from './request'

export interface OrgResponse {
  org_id: string; name: string; description: string | null
  created_by: string; role: string | null; created_at: string | null; updated_at: string | null
}
export interface MemberResponse {
  membership_id: string; org_id: string; user_id: string
  username: string; display_name: string | null; role: string; joined_at: string | null
}
export interface CreateOrgRequest { name: string; description?: string }
export interface UpdateOrgRequest { name?: string; description?: string }
export interface InviteMemberRequest { username: string }
export interface ChangeRoleRequest { role: 'admin' | 'member' }

export const createOrg = (data: CreateOrgRequest) => request.post<any, OrgResponse>('/orgs', data)
export const listMyOrgs = () => request.get<any, OrgResponse[]>('/orgs')
export const getOrg = (orgId: string) => request.get<any, OrgResponse>(`/orgs/${orgId}`)
export const updateOrg = (orgId: string, data: UpdateOrgRequest) =>
  request.patch<any, OrgResponse>(`/orgs/${orgId}`, data)
export const listMembers = (orgId: string) =>
  request.get<any, MemberResponse[]>(`/orgs/${orgId}/members`)
export const inviteMember = (orgId: string, data: InviteMemberRequest) =>
  request.post<any, { invitation_id: string }>(`/orgs/${orgId}/invitations`, data)
export const changeMemberRole = (orgId: string, userId: string, data: ChangeRoleRequest) =>
  request.patch<any, MemberResponse>(`/orgs/${orgId}/members/${userId}`, data)
export const removeMember = (orgId: string, userId: string) =>
  request.delete<any, { detail: string }>(`/orgs/${orgId}/members/${userId}`)
export const leaveOrg = (orgId: string) =>
  request.delete<any, { detail: string }>(`/orgs/${orgId}/members/me`)
