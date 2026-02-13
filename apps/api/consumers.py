"""
WebSocket Consumers for Real-Time Sync
Provides real-time updates for students, teachers, and classrooms

Requires: pip install channels channels-redis
"""
import json

# Try to import channels, fallback gracefully if not installed
try:
    from channels.generic.websocket import AsyncWebsocketConsumer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False
    # Create dummy classes for when channels is not installed
    class AsyncWebsocketConsumer:
        pass

from django.contrib.auth import get_user_model

User = get_user_model()


class StudentSyncConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for student data synchronization"""
    
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.room_group_name = f"students_sync_{self.user.id}"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        
        # Echo message back (for testing)
        await self.send(text_data=json.dumps({
            "message": f"Received: {message}"
        }))
    
    # Receive message from room group
    async def student_update(self, event):
        message = event["message"]
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            "type": "student_update",
            "message": message
        }))


class TeacherSyncConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for teacher data synchronization"""
    
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.room_group_name = f"teachers_sync_{self.user.id}"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        
        await self.send(text_data=json.dumps({
            "message": f"Received: {message}"
        }))
    
    async def teacher_update(self, event):
        message = event["message"]
        
        await self.send(text_data=json.dumps({
            "type": "teacher_update",
            "message": message
        }))


class ClassroomSyncConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for classroom data synchronization"""
    
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.room_group_name = f"classrooms_sync_{self.user.id}"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        
        await self.send(text_data=json.dumps({
            "message": f"Received: {message}"
        }))
    
    async def classroom_update(self, event):
        message = event["message"]
        
        await self.send(text_data=json.dumps({
            "type": "classroom_update",
            "message": message
        }))
