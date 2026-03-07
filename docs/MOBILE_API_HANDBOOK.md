# Mobile API Integration Handbook

**Project**: School Management System - Mobile API Layer  
**Version**: 1.0  
**Phase**: 9 - Innovation Features  
**Last Updated**: January 2026

---

## Table of Contents
1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Authentication](#authentication)
4. [API Endpoints](#api-endpoints)
5. [Models Reference](#models-reference)
6. [Offline Sync](#offline-sync)
7. [Push Notifications](#push-notifications)
8. [Error Handling](#error-handling)
9. [Rate Limiting](#rate-limiting)
10. [Best Practices](#best-practices)
11. [Code Examples](#code-examples)

---

## Overview

The Mobile API provides REST endpoints for building native iOS, Android, and web applications. It enables students, parents, and teachers to access school data on mobile devices with offline capabilities.

### Key Features
- ✅ JWT authentication (access + refresh tokens)
- ✅ Device registration and management
- ✅ Push notifications
- ✅ Offline sync queue with conflict resolution
- ✅ Rate limiting (100 requests/hour authenticated, 20/hour anonymous)
- ✅ RESTful design following Django REST Framework conventions

### Architecture
```
Mobile App (iOS/Android/Web)
         ↓
    JWT Auth
         ↓
Mobile API Endpoints (/api/mobile/*)
         ↓
Django ORM → PostgreSQL
         ↓
Existing Phase 8 Infrastructure
  - Portal (apps.portal)
  - People (apps.people)
  - Academics (apps.academics)
```

---

## Quick Start

### 1. Installation

Add to `requirements.txt`:
```python
djangorestframework>=3.14.0
djangorestframework-simplejwt>=5.2.0
```

Install:
```bash
pip install -r requirements.txt
```

### 2. Settings Configuration

In `config/settings.py`:

```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'rest_framework_simplejwt',
    'apps.api',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'apps.api.mobile_api.MobileRateThrottle',
        'apps.api.mobile_api.MobileAnonRateThrottle',
    ],
}

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}
```

### 3. URL Configuration

In `config/urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path('api/mobile/', include('apps.api.urls')),
]
```

### 4. Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Test the API

```bash
# Start development server
python manage.py runserver

# Test authentication
curl -X POST http://localhost:8000/api/mobile/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "student1", "password": "password123"}'
```

---

## Authentication

### JWT Token Workflow

1. **Obtain Tokens** (Login)
2. **Use Access Token** (API calls)
3. **Refresh Access Token** (when expired)
4. **Logout** (optional - client-side token deletion)

### 1. Obtain JWT Tokens

**Endpoint**: `POST /api/mobile/auth/token/`

**Request**:
```json
{
  "username": "student1",
  "password": "password123"
}
```

**Response**:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Access Token**: Valid for 1 hour  
**Refresh Token**: Valid for 7 days

### 2. Use Access Token

Include in Authorization header for all API calls:

```bash
curl -X GET http://localhost:8000/api/mobile/devices/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

### 3. Refresh Access Token

**Endpoint**: `POST /api/mobile/auth/token/refresh/`

**Request**:
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response**:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."  // New refresh token (rotated)
}
```

### 4. Error Responses

**Invalid Credentials (401)**:
```json
{
  "detail": "No active account found with the given credentials"
}
```

**Token Expired (401)**:
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

---

## API Endpoints

### Base URL
```
Production: https://yourdomain.com/api/mobile/
Development: http://localhost:8000/api/mobile/
```

### Endpoint Summary

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/auth/token/` | Obtain JWT tokens | No |
| POST | `/auth/token/refresh/` | Refresh access token | No |
| GET | `/devices/` | List user's devices | Yes |
| POST | `/devices/` | Register new device | Yes |
| PATCH | `/devices/{id}/` | Update device (push token) | Yes |
| DELETE | `/devices/{id}/` | Deactivate device | Yes |
| GET | `/notifications/` | List notifications | Yes |
| POST | `/notifications/{id}/mark_delivered/` | Mark notification delivered | Yes |
| GET | `/sync/` | Get sync queue items | Yes |
| POST | `/sync/` | Submit data for sync | Yes |
| POST | `/sync/{id}/mark_synced/` | Mark item synced | Yes |

---

## Models Reference

### 1. MobileDevice

Represents a registered mobile device.

**Fields**:
- `user` (ForeignKey): Device owner
- `device_id` (CharField): Unique device identifier (UUID)
- `device_name` (CharField): User-friendly name (e.g., "John's iPhone")
- `platform` (CharField): iOS, Android, or Web
- `platform_version` (CharField): OS version
- `app_version` (CharField): App version
- `push_token` (CharField): FCM/APNS push notification token
- `last_active` (DateTimeField): Last API call timestamp
- `is_active` (Boolean): Device active status

**Methods**:
- `deactivate()`: Mark device inactive

**Example**:
```python
from apps.api.mobile_api import MobileDevice

device = MobileDevice.objects.create(
    user=user,
    device_id='abc123',
    device_name="John's iPhone",
    platform='iOS',
    push_token='fcm_token_here'
)
```

---

### 2. PushNotification

Push notification messages.

**Fields**:
- `user` (ForeignKey): Recipient
- `title` (CharField): Notification title
- `body` (TextField): Notification body
- `data` (JSONField): Additional payload
- `notification_type` (CharField): GRADE_POSTED, ATTENDANCE_ALERT, etc.
- `status` (CharField): PENDING, SENT, FAILED, DELIVERED
- `sent_at` (DateTimeField): Sent timestamp
- `delivered_at` (DateTimeField): Delivered timestamp

**Methods**:
- `mark_delivered()`: Update delivery status

**Example**:
```python
from apps.api.mobile_api import PushNotification

notification = PushNotification.objects.create(
    user=student,
    title='New Grade Posted',
    body='Your Math grade is now available',
    notification_type='GRADE_POSTED',
    data={'subject_id': 123, 'grade': 85}
)
```

---

### 3. OfflineSyncQueue

Offline data synchronization queue.

**Fields**:
- `user` (ForeignKey): User who created the change
- `model_name` (CharField): Django model name
- `object_id` (Integer): Primary key of the object
- `action` (CharField): CREATE, UPDATE, DELETE
- `data` (JSONField): Changed data
- `status` (CharField): PENDING, SYNCING, COMPLETED, CONFLICT, FAILED
- `created_at` (DateTimeField): Queue entry timestamp
- `synced_at` (DateTimeField): Sync completion timestamp
- `conflict_data` (JSONField): Server data if conflict

**Methods**:
- `mark_synced()`: Mark successfully synced
- `mark_conflict()`: Mark as conflict

**Example**:
```python
from apps.api.mobile_api import OfflineSyncQueue

# Mobile app creates offline entry
sync_item = OfflineSyncQueue.objects.create(
    user=student,
    model_name='Grade',
    object_id=456,
    action='UPDATE',
    data={'score': 90, 'notes': 'Improved'}
)

# Later, sync with server
sync_item.mark_synced()
```

---

### 4. APIAccessLog

API request logging and monitoring.

**Fields**:
- `user` (ForeignKey): Requesting user
- `device` (ForeignKey): Device making request
- `endpoint` (CharField): API endpoint path
- `method` (CharField): HTTP method (GET, POST, etc.)
- `status_code` (Integer): HTTP status code
- `response_time_ms` (Integer): Response time in milliseconds
- `request_size_bytes` (Integer): Request payload size
- `response_size_bytes` (Integer): Response payload size
- `timestamp` (DateTimeField): Request timestamp

**Example** (auto-logged by middleware):
```python
# Automatically logged by Django middleware
# Check logs:
from apps.api.mobile_api import APIAccessLog

recent_logs = APIAccessLog.objects.filter(
    user=student
).order_by('-timestamp')[:10]
```

---

## Offline Sync

### How Offline Sync Works

1. **Mobile app operates offline**
   - User makes changes (e.g., updates profile, saves notes)
   - Changes queued locally in mobile app database

2. **App comes online**
   - Mobile app sends queued changes to `/api/mobile/sync/`

3. **Server processes sync**
   - Validates data
   - Checks for conflicts (server data changed since last sync)
   - If no conflict: applies changes, marks COMPLETED
   - If conflict: marks CONFLICT, returns server data for resolution

4. **Mobile app handles result**
   - If COMPLETED: delete local queue item
   - If CONFLICT: prompt user to resolve (keep local or server version)

### API Endpoints

#### Submit Data for Sync

**Endpoint**: `POST /api/mobile/sync/`

**Request**:
```json
{
  "model_name": "StudentProfile",
  "object_id": 123,
  "action": "UPDATE",
  "data": {
    "phone": "+1234567890",
    "emergency_contact": "Jane Doe"
  }
}
```

**Response (Success)**:
```json
{
  "id": 456,
  "status": "PENDING",
  "created_at": "2026-01-18T10:30:00Z"
}
```

**Response (Conflict)**:
```json
{
  "id": 456,
  "status": "CONFLICT",
  "conflict_data": {
    "phone": "+9876543210",  // Server has different data
    "emergency_contact": "John Doe"
  },
  "message": "Data conflict detected. Please resolve."
}
```

#### Get Sync Queue

**Endpoint**: `GET /api/mobile/sync/`

**Response**:
```json
[
  {
    "id": 456,
    "model_name": "StudentProfile",
    "object_id": 123,
    "action": "UPDATE",
    "data": {"phone": "+1234567890"},
    "status": "PENDING",
    "created_at": "2026-01-18T10:30:00Z"
  }
]
```

#### Mark Item Synced

**Endpoint**: `POST /api/mobile/sync/{id}/mark_synced/`

**Response**:
```json
{
  "id": 456,
  "status": "COMPLETED",
  "synced_at": "2026-01-18T10:35:00Z"
}
```

### Conflict Resolution Strategy

**Option 1: Server Wins**
```python
# Mobile app discards local changes, uses server data
sync_item = get_sync_item(456)
local_data = sync_item.conflict_data  # Use server version
```

**Option 2: Client Wins**
```python
# Resubmit local changes with force flag
requests.post('/api/mobile/sync/', json={
    'model_name': 'StudentProfile',
    'object_id': 123,
    'action': 'UPDATE',
    'data': local_data,
    'force': True  # Override server data
})
```

**Option 3: Manual Merge**
```python
# User reviews both versions and selects fields to keep
merged_data = {
    'phone': local_data['phone'],  # Keep local
    'emergency_contact': server_data['emergency_contact']  # Keep server
}
```

---

## Push Notifications

### Setup

#### 1. Configure FCM/APNS

**Firebase Cloud Messaging (Android)**:
- Create Firebase project
- Download `google-services.json`
- Add to Android app

**Apple Push Notification Service (iOS)**:
- Create APNs certificate in Apple Developer Portal
- Upload to Firebase project

#### 2. Register Device

**Endpoint**: `POST /api/mobile/devices/`

**Request**:
```json
{
  "device_id": "abc123-def456",
  "device_name": "John's iPhone",
  "platform": "iOS",
  "platform_version": "17.2",
  "app_version": "1.0.0",
  "push_token": "fcm_token_here"
}
```

#### 3. Update Push Token (when it changes)

**Endpoint**: `PATCH /api/mobile/devices/{id}/`

**Request**:
```json
{
  "push_token": "new_fcm_token_here"
}
```

### Sending Notifications (Server-Side)

```python
from apps.api.mobile_api import PushNotification, MobileDevice

# Create notification
notification = PushNotification.objects.create(
    user=student,
    title='New Grade Posted',
    body='Your Math grade is now available',
    notification_type='GRADE_POSTED',
    data={'subject_id': 123, 'grade': 85}
)

# Send to user's devices
devices = MobileDevice.objects.filter(user=student, is_active=True)

for device in devices:
    # Use FCM SDK or HTTP API
    import requests
    
    fcm_url = 'https://fcm.googleapis.com/fcm/send'
    headers = {
        'Authorization': 'key=YOUR_FCM_SERVER_KEY',
        'Content-Type': 'application/json'
    }
    payload = {
        'to': device.push_token,
        'notification': {
            'title': notification.title,
            'body': notification.body,
        },
        'data': notification.data
    }
    
    response = requests.post(fcm_url, json=payload, headers=headers)
    
    if response.status_code == 200:
        notification.status = 'SENT'
        notification.sent_at = timezone.now()
        notification.save()
```

### Notification Types

Predefined types in `PushNotification.NOTIFICATION_TYPES`:
- `GRADE_POSTED`: New grade available
- `ATTENDANCE_ALERT`: Attendance issue
- `FEE_DUE`: Payment reminder
- `ANNOUNCEMENT`: School announcement
- `MESSAGE`: Direct message
- `SCHEDULE_CHANGE`: Timetable update
- `EXAM_REMINDER`: Upcoming exam

---

## Error Handling

### Standard Error Response Format

```json
{
  "error": "ErrorCode",
  "message": "Human-readable error message",
  "details": {
    "field": ["Error details"]
  }
}
```

### Common Error Codes

| Status Code | Error | Description |
|-------------|-------|-------------|
| 400 | BAD_REQUEST | Invalid request data |
| 401 | UNAUTHORIZED | Missing or invalid token |
| 403 | FORBIDDEN | Insufficient permissions |
| 404 | NOT_FOUND | Resource not found |
| 429 | RATE_LIMIT_EXCEEDED | Too many requests |
| 500 | SERVER_ERROR | Internal server error |

### Example Error Responses

**400 Bad Request**:
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Invalid device platform",
  "details": {
    "platform": ["Must be one of: iOS, Android, Web"]
  }
}
```

**429 Rate Limit**:
```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Request limit exceeded. Try again in 1 hour.",
  "retry_after": 3600
}
```

---

## Rate Limiting

### Throttle Classes

#### 1. MobileRateThrottle
- **Scope**: Authenticated users
- **Limit**: 100 requests per hour
- **Cache Key**: `mobile_throttle_{user_id}`

#### 2. MobileAnonRateThrottle
- **Scope**: Anonymous users
- **Limit**: 20 requests per hour
- **Cache Key**: `mobile_anon_throttle_{ip_address}`

### Checking Rate Limit Status

Headers included in every response:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642518000  // Unix timestamp
```

### Handling Rate Limits

**Client-Side**:
```javascript
// Check headers after each request
const remainingRequests = response.headers['X-RateLimit-Remaining'];
const resetTime = response.headers['X-RateLimit-Reset'];

if (remainingRequests < 10) {
  // Warn user: "Low API credits remaining"
}

if (response.status === 429) {
  const retryAfter = response.headers['Retry-After'];
  // Wait retryAfter seconds before retrying
}
```

### Custom Throttle Configuration

In `settings.py`:
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'mobile': '100/hour',      # MobileRateThrottle
        'mobile_anon': '20/hour',  # MobileAnonRateThrottle
    }
}
```

---

## Best Practices

### 1. Token Management

✅ **Store tokens securely**:
- iOS: Keychain
- Android: EncryptedSharedPreferences
- Web: HttpOnly cookies (not localStorage)

✅ **Refresh tokens proactively**:
```javascript
// Refresh 5 minutes before expiration
if (tokenExpiresIn < 5 * 60) {
  refreshAccessToken();
}
```

✅ **Handle token expiration gracefully**:
```javascript
async function apiCall(endpoint, options) {
  let response = await fetch(endpoint, options);
  
  if (response.status === 401) {
    // Token expired, refresh
    await refreshAccessToken();
    // Retry original request
    response = await fetch(endpoint, options);
  }
  
  return response;
}
```

### 2. Offline-First Design

✅ **Queue actions locally**:
```javascript
// User action (offline)
await localDB.queue({
  model: 'Grade',
  action: 'UPDATE',
  data: {id: 123, notes: 'Updated offline'}
});

// When online
const queuedItems = await localDB.getQueue();
for (const item of queuedItems) {
  await syncToServer(item);
}
```

✅ **Show sync status to user**:
```
⏳ Syncing 3 items...
✅ Synced successfully
⚠️ 1 conflict - review needed
```

### 3. Push Notification Best Practices

✅ **Request permission at appropriate time**:
```javascript
// Don't request on app launch
// Request when user enables a feature that needs notifications
if (userEnabledGradeNotifications) {
  requestPushPermission();
}
```

✅ **Handle notification taps**:
```javascript
// iOS example
func userNotificationCenter(_ center: UNUserNotificationCenter,
                           didReceive response: UNNotificationResponse) {
  let data = response.notification.request.content.userInfo
  if data['notification_type'] == 'GRADE_POSTED' {
    navigateToGrades(subjectId: data['subject_id'])
  }
}
```

### 4. Error Handling

✅ **Retry failed requests with exponential backoff**:
```javascript
async function retryRequest(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(2 ** i * 1000);  // 1s, 2s, 4s
    }
  }
}
```

✅ **Provide helpful error messages**:
```javascript
catch (error) {
  if (error.status === 429) {
    showMessage('Too many requests. Please wait a moment.');
  } else if (error.status === 500) {
    showMessage('Server error. Please try again later.');
  } else {
    showMessage('Something went wrong. Check your connection.');
  }
}
```

### 5. Performance Optimization

✅ **Paginate large lists**:
```javascript
// Fetch grades in pages
const grades = await fetch('/api/mobile/grades/?page=1&page_size=20');
```

✅ **Cache responses**:
```javascript
// Cache for 5 minutes
const cacheKey = 'schedule_' + date;
let schedule = cache.get(cacheKey);

if (!schedule) {
  schedule = await fetchSchedule(date);
  cache.set(cacheKey, schedule, 5 * 60);
}
```

✅ **Use WebSockets for real-time data** (optional):
```javascript
// Connect to WebSocket for live updates
const ws = new WebSocket('wss://yourdomain.com/ws/notifications/');
ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  showNotification(notification);
};
```

---

## Code Examples

### iOS (Swift)

#### 1. Authentication

```swift
import Foundation

class APIClient {
    let baseURL = "https://yourdomain.com/api/mobile"
    var accessToken: String?
    var refreshToken: String?
    
    func login(username: String, password: String) async throws {
        let url = URL(string: "\(baseURL)/auth/token/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ["username": username, "password": password]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let response = try JSONDecoder().decode(TokenResponse.self, from: data)
        
        self.accessToken = response.access
        self.refreshToken = response.refresh
        
        // Store in Keychain
        KeychainHelper.save(token: response.access, key: "accessToken")
        KeychainHelper.save(token: response.refresh, key: "refreshToken")
    }
    
    func refreshAccessToken() async throws {
        guard let refreshToken = self.refreshToken else { return }
        
        let url = URL(string: "\(baseURL)/auth/token/refresh/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ["refresh": refreshToken]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let response = try JSONDecoder().decode(TokenResponse.self, from: data)
        
        self.accessToken = response.access
        KeychainHelper.save(token: response.access, key: "accessToken")
    }
}

struct TokenResponse: Codable {
    let access: String
    let refresh: String
}
```

#### 2. Register Device

```swift
func registerDevice(pushToken: String) async throws {
    let url = URL(string: "\(baseURL)/devices/")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(accessToken!)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    
    let deviceId = UIDevice.current.identifierForVendor?.uuidString ?? ""
    let body: [String: Any] = [
        "device_id": deviceId,
        "device_name": UIDevice.current.name,
        "platform": "iOS",
        "platform_version": UIDevice.current.systemVersion,
        "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0",
        "push_token": pushToken
    ]
    
    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    
    let (_, response) = try await URLSession.shared.data(for: request)
    
    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 201 else {
        throw APIError.deviceRegistrationFailed
    }
}
```

### Android (Kotlin)

#### 1. Authentication

```kotlin
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

interface APIService {
    @POST("auth/token/")
    suspend fun login(@Body credentials: LoginRequest): TokenResponse
    
    @POST("auth/token/refresh/")
    suspend fun refreshToken(@Body refresh: RefreshRequest): TokenResponse
    
    @GET("devices/")
    suspend fun getDevices(@Header("Authorization") token: String): List<Device>
    
    @POST("devices/")
    suspend fun registerDevice(
        @Header("Authorization") token: String,
        @Body device: DeviceRequest
    ): Device
}

data class LoginRequest(val username: String, val password: String)
data class RefreshRequest(val refresh: String)
data class TokenResponse(val access: String, val refresh: String)

class APIClient {
    private val retrofit = Retrofit.Builder()
        .baseUrl("https://yourdomain.com/api/mobile/")
        .addConverterFactory(GsonConverterFactory.create())
        .build()
    
    val api: APIService = retrofit.create(APIService::class.java)
    
    var accessToken: String? = null
    var refreshToken: String? = null
    
    suspend fun login(username: String, password: String) {
        val response = api.login(LoginRequest(username, password))
        accessToken = response.access
        refreshToken = response.refresh
        
        // Store in EncryptedSharedPreferences
        val prefs = EncryptedSharedPreferences.create(...)
        prefs.edit()
            .putString("accessToken", accessToken)
            .putString("refreshToken", refreshToken)
            .apply()
    }
}
```

#### 2. Register Device with FCM

```kotlin
import com.google.firebase.messaging.FirebaseMessaging

class DeviceRegistration {
    suspend fun registerDevice(apiClient: APIClient) {
        FirebaseMessaging.getInstance().token.await().let { token ->
            val deviceRequest = DeviceRequest(
                deviceId = Settings.Secure.getString(
                    context.contentResolver,
                    Settings.Secure.ANDROID_ID
                ),
                deviceName = "${Build.MANUFACTURER} ${Build.MODEL}",
                platform = "Android",
                platformVersion = Build.VERSION.RELEASE,
                appVersion = BuildConfig.VERSION_NAME,
                pushToken = token
            )
            
            apiClient.api.registerDevice(
                "Bearer ${apiClient.accessToken}",
                deviceRequest
            )
        }
    }
}

data class DeviceRequest(
    val deviceId: String,
    val deviceName: String,
    val platform: String,
    val platformVersion: String,
    val appVersion: String,
    val pushToken: String
)
```

### React Native (JavaScript)

#### 1. API Client with Auto-Refresh

```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';

const API_BASE = 'https://yourdomain.com/api/mobile';

class APIClient {
  constructor() {
    this.accessToken = null;
    this.refreshToken = null;
    
    // Create axios instance
    this.client = axios.create({
      baseURL: API_BASE,
      timeout: 10000,
    });
    
    // Add request interceptor to add auth header
    this.client.interceptors.request.use(
      async (config) => {
        const token = await this.getAccessToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );
    
    // Add response interceptor to handle 401 and refresh token
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          
          try {
            await this.refreshAccessToken();
            return this.client(originalRequest);
          } catch (refreshError) {
            // Refresh failed, logout user
            await this.logout();
            return Promise.reject(refreshError);
          }
        }
        
        return Promise.reject(error);
      }
    );
  }
  
  async login(username, password) {
    const response = await this.client.post('/auth/token/', {
      username,
      password,
    });
    
    this.accessToken = response.data.access;
    this.refreshToken = response.data.refresh;
    
    await AsyncStorage.setItem('accessToken', this.accessToken);
    await AsyncStorage.setItem('refreshToken', this.refreshToken);
    
    return response.data;
  }
  
  async refreshAccessToken() {
    const refreshToken = await AsyncStorage.getItem('refreshToken');
    
    const response = await axios.post(`${API_BASE}/auth/token/refresh/`, {
      refresh: refreshToken,
    });
    
    this.accessToken = response.data.access;
    await AsyncStorage.setItem('accessToken', this.accessToken);
    
    return response.data;
  }
  
  async getAccessToken() {
    if (!this.accessToken) {
      this.accessToken = await AsyncStorage.getItem('accessToken');
    }
    return this.accessToken;
  }
  
  async logout() {
    this.accessToken = null;
    this.refreshToken = null;
    await AsyncStorage.removeItem('accessToken');
    await AsyncStorage.removeItem('refreshToken');
  }
  
  // API Methods
  async getDevices() {
    const response = await this.client.get('/devices/');
    return response.data;
  }
  
  async registerDevice(deviceData) {
    const response = await this.client.post('/devices/', deviceData);
    return response.data;
  }
  
  async getNotifications() {
    const response = await this.client.get('/notifications/');
    return response.data;
  }
  
  async getSyncQueue() {
    const response = await this.client.get('/sync/');
    return response.data;
  }
  
  async submitSync(syncData) {
    const response = await this.client.post('/sync/', syncData);
    return response.data;
  }
}

export default new APIClient();
```

#### 2. Offline Sync Manager

```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import APIClient from './APIClient';

class OfflineSyncManager {
  constructor() {
    this.syncQueueKey = 'offline_sync_queue';
    
    // Listen for network changes
    NetInfo.addEventListener((state) => {
      if (state.isConnected) {
        this.processQueue();
      }
    });
  }
  
  async queueChange(modelName, objectId, action, data) {
    const queue = await this.getQueue();
    
    queue.push({
      id: Date.now(),
      modelName,
      objectId,
      action,
      data,
      timestamp: new Date().toISOString(),
    });
    
    await AsyncStorage.setItem(this.syncQueueKey, JSON.stringify(queue));
  }
  
  async getQueue() {
    const queueJSON = await AsyncStorage.getItem(this.syncQueueKey);
    return queueJSON ? JSON.parse(queueJSON) : [];
  }
  
  async processQueue() {
    const queue = await this.getQueue();
    
    if (queue.length === 0) return;
    
    const results = { success: 0, failed: 0, conflicts: [] };
    
    for (const item of queue) {
      try {
        const response = await APIClient.submitSync({
          model_name: item.modelName,
          object_id: item.objectId,
          action: item.action,
          data: item.data,
        });
        
        if (response.status === 'COMPLETED') {
          results.success++;
          // Remove from queue
          await this.removeFromQueue(item.id);
        } else if (response.status === 'CONFLICT') {
          results.conflicts.push({
            item,
            serverData: response.conflict_data,
          });
        }
      } catch (error) {
        results.failed++;
      }
    }
    
    return results;
  }
  
  async removeFromQueue(itemId) {
    const queue = await this.getQueue();
    const newQueue = queue.filter((item) => item.id !== itemId);
    await AsyncStorage.setItem(this.syncQueueKey, JSON.stringify(newQueue));
  }
}

export default new OfflineSyncManager();
```

---

## Troubleshooting

### Common Issues

#### 1. 401 Unauthorized
**Problem**: Token invalid or expired

**Solutions**:
- Check token format: `Bearer {token}`
- Verify token hasn't expired (1 hour lifetime)
- Try refreshing token

#### 2. 429 Rate Limit Exceeded
**Problem**: Too many requests

**Solutions**:
- Implement exponential backoff
- Cache responses to reduce API calls
- Check `X-RateLimit-Remaining` header

#### 3. Device Registration Fails
**Problem**: Push token invalid

**Solutions**:
- Verify FCM/APNS configuration
- Check push token format
- Ensure platform field matches device

#### 4. Offline Sync Conflicts
**Problem**: Server data changed while offline

**Solutions**:
- Implement conflict resolution UI
- Allow user to choose version
- Consider last-write-wins strategy

---

## Support

For issues or questions:
- **Email**: support@schooldomain.com
- **Documentation**: https://docs.schooldomain.com/mobile-api
- **GitHub**: https://github.com/yourorg/school-management

---

**Version**: 1.0  
**Last Updated**: January 2026  
**License**: Proprietary
