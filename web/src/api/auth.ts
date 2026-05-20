import request from './request'

export interface RegisterRequest {
  username: string
  password: string
  display_name?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserResponse {
  user_id: string
  username: string
  display_name: string | null
  created_at: string | null
  organizations: {
    org_id: string
    org_name: string
    role: string
  }[]
}

export interface InvitationResponse {
  invitation_id: string
  org_id: string
  org_name: string
  inviter_user_id: string
  inviter_username: string
  invitee_user_id: string
  status: string
  created_at: string | null
  responded_at: string | null
  expired: boolean
}

export const register = (data: RegisterRequest) =>
  request.post<any, UserResponse>('/auth/register', data)

export const login = (data: LoginRequest) =>
  request.post<any, TokenResponse>('/auth/login', data)

export const refreshToken = () =>
  request.post<any, TokenResponse>('/auth/refresh')

export const getMe = () =>
  request.get<any, UserResponse>('/auth/me')

export const switchOrg = (orgId: string) =>
  request.post<any, TokenResponse>('/auth/switch-org', { org_id: orgId })

export const getMyInvitations = () =>
  request.get<any, InvitationResponse[]>('/auth/invitations')

export const acceptInvitation = (invitationId: string) =>
  request.post<any, { detail: string }>(`/auth/invitations/${invitationId}/accept`)

export const rejectInvitation = (invitationId: string) =>
  request.post<any, { detail: string }>(`/auth/invitations/${invitationId}/reject`)
