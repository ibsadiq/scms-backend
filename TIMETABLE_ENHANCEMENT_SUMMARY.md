# Teacher Dashboard Timetable Enhancement

**Date**: 2025-12-04
**Enhancement to**: Phase 1.3 - Teacher Permissions & Workflows

---

## 🎯 What Was Added

Enhanced the teacher dashboard to include **real-time timetable information**, showing teachers their schedule for the day with visual indicators for current, past, and upcoming periods.

---

## ✨ New Features

### 1. **Today's Schedule in Dashboard**

The dashboard (`GET /api/examination/teacher/dashboard/`) now includes:

- **Today's full schedule** (`todays_schedule`)
- **Next upcoming period** (`next_period`)
- **Period count for today** (`periods_today` in summary)
- **Current day and time** (`current_day`, `current_time`)

### 2. **Period Status Indicators**

Each period in today's schedule includes a `status` field:
- `past` - Period has already ended
- `current` - Period is happening right now
- `upcoming` - Period hasn't started yet

### 3. **Full Week Timetable Endpoint**

New endpoint: `GET /api/examination/teacher/my-timetable/`

- View entire week's schedule organized by day
- Filter by specific day with `?day=Monday`
- Shows all periods with times, classrooms, and room numbers

---

## 📊 Enhanced Dashboard Response

```json
{
  "teacher_name": "John Doe",
  "current_day": "Wednesday",
  "current_time": "10:30",
  "summary": {
    "classrooms": 3,
    "subjects": 2,
    "total_students": 105,
    "marks_entered": 250,
    "periods_today": 4  // NEW
  },
  "todays_schedule": [  // NEW
    {
      "id": 45,
      "subject": "Mathematics",
      "classroom": "Primary 4 A",
      "start_time": "08:00",
      "end_time": "09:00",
      "room_number": "Room 201",
      "status": "past",
      "notes": null
    },
    {
      "id": 46,
      "subject": "English",
      "classroom": "Primary 4 B",
      "start_time": "10:00",
      "end_time": "11:00",
      "room_number": "Room 203",
      "status": "current",  // Currently teaching
      "notes": null
    },
    {
      "id": 47,
      "subject": "Mathematics",
      "classroom": "Primary 5 A",
      "start_time": "11:30",
      "end_time": "12:30",
      "room_number": "Room 201",
      "status": "upcoming",
      "notes": null
    }
  ],
  "next_period": {  // NEW - Quick access to next class
    "id": 47,
    "subject": "Mathematics",
    "classroom": "Primary 5 A",
    "start_time": "11:30",
    "end_time": "12:30",
    "room_number": "Room 201",
    "status": "upcoming",
    "notes": null
  }
}
```

---

## 🔌 New API Endpoints

### Get Full Week Timetable

```http
GET /api/examination/teacher/my-timetable/
Authorization: Bearer {token}
```

**Response**:
```json
{
  "teacher": "John Doe",
  "timetable": {
    "Monday": [
      {
        "id": 1,
        "subject": "Mathematics",
        "classroom": "Primary 4 A",
        "start_time": "08:00",
        "end_time": "09:00",
        "room_number": "Room 201",
        "notes": null
      },
      {
        "id": 2,
        "subject": "English",
        "classroom": "Primary 4 B",
        "start_time": "10:00",
        "end_time": "11:00",
        "room_number": "Room 203",
        "notes": null
      }
    ],
    "Tuesday": [...],
    "Wednesday": [...],
    "Thursday": [...],
    "Friday": [...]
  }
}
```

### Filter by Specific Day

```http
GET /api/examination/teacher/my-timetable/?day=Monday
Authorization: Bearer {token}
```

---

## 🎨 Frontend Use Cases

### 1. **Dashboard Display**

```javascript
// Show current class prominently
const currentPeriod = dashboard.todays_schedule.find(p => p.status === 'current');
if (currentPeriod) {
  displayBanner(`Currently Teaching: ${currentPeriod.subject} - ${currentPeriod.classroom}`);
}

// Show next class
if (dashboard.next_period) {
  displayNextClass(`Next: ${dashboard.next_period.subject} at ${dashboard.next_period.start_time}`);
}
```

### 2. **Daily Schedule View**

```javascript
// Color-code periods by status
dashboard.todays_schedule.forEach(period => {
  const color = {
    past: 'gray',
    current: 'green',
    upcoming: 'blue'
  }[period.status];

  renderPeriod(period, color);
});
```

### 3. **Week View Calendar**

```javascript
// Display full week timetable
fetch('/api/examination/teacher/my-timetable/')
  .then(res => res.json())
  .then(data => {
    renderWeekCalendar(data.timetable);
  });
```

---

## 💡 Benefits

### For Teachers:
- ✅ See current class at a glance
- ✅ Know what's coming next
- ✅ Plan day more effectively
- ✅ Quick access to room numbers
- ✅ View full week schedule

### For School Admin:
- ✅ Teachers always aware of schedule
- ✅ Reduces missed classes
- ✅ Better time management
- ✅ Real-time schedule awareness

---

## 🔄 How It Works

### Time-Based Status Calculation

```python
current_time = timezone.now().time()

for period in todays_periods:
    if current_time >= period.end_time:
        status = 'past'
    elif current_time >= period.start_time and current_time < period.end_time:
        status = 'current'
    else:
        status = 'upcoming'
```

### Day Detection

```python
today = timezone.now()
day_name = today.strftime('%A')  # 'Monday', 'Tuesday', etc.

periods = Period.objects.filter(
    teacher=teacher,
    day_of_week=day_name,
    is_active=True
).order_by('start_time')
```

---

## 📝 Data Requirements

For timetable to work, the following must be configured:

1. **Period Records**: Create Period entries in the schedule module
2. **Teacher Assignment**: Link periods to teachers
3. **Active Status**: Ensure `is_active=True` on current periods
4. **Time Configuration**: Set correct start_time and end_time

### Example Period Creation

```python
from schedule.models import Period
from academic.models import Teacher, ClassRoom, AllocatedSubject

period = Period.objects.create(
    day_of_week='Monday',
    start_time='08:00',
    end_time='09:00',
    classroom=classroom,
    subject=allocated_subject,  # AllocatedSubject instance
    teacher=teacher,
    room_number='Room 201',
    is_active=True
)
```

---

## 🧪 Testing

### Test Dashboard with Timetable

```bash
# 1. Create test periods for a teacher
# 2. Login as teacher
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "teacher1", "password": "password"}'

# 3. Get dashboard
curl -X GET http://localhost:8000/api/examination/teacher/dashboard/ \
  -H "Authorization: Bearer {token}"

# 4. Check todays_schedule array
# 5. Verify next_period is populated
# 6. Confirm period statuses are correct
```

### Test Full Timetable

```bash
# Get full week
curl -X GET http://localhost:8000/api/examination/teacher/my-timetable/ \
  -H "Authorization: Bearer {token}"

# Get specific day
curl -X GET "http://localhost:8000/api/examination/teacher/my-timetable/?day=Monday" \
  -H "Authorization: Bearer {token}"
```

---

## 🔧 Configuration

### School Day Settings (Optional Enhancement)

You can configure school day settings:

```python
# In settings.py
SCHOOL_START_TIME = '08:00'
SCHOOL_END_TIME = '16:00'
SCHOOL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
```

### Break Times (Optional Enhancement)

Add break periods that don't show as classes:

```python
period = Period.objects.create(
    day_of_week='Monday',
    start_time='10:30',
    end_time='10:45',
    classroom=None,  # Break applies to all
    subject=None,
    teacher=teacher,
    notes='Break Time',
    is_active=True
)
```

---

## 📱 Mobile App Benefits

This enhancement is particularly useful for mobile apps:

### Dashboard Widget
- Show current class
- Countdown to next period
- Quick access to room number

### Notifications
- "Class starting in 5 minutes"
- "You have Mathematics in Room 201 next"
- "Free period for the next hour"

### Calendar Integration
- Sync timetable to phone calendar
- Set automatic reminders
- Show week view

---

## ✅ Files Modified

- `examination/views_teacher.py` - Enhanced dashboard method, added my_timetable endpoint
- `PHASE_1_3_TEACHER_PERMISSIONS_SUMMARY.md` - Updated documentation

**No migrations required** - Uses existing Period model from schedule module.

---

## 🚀 Next Enhancements (Optional)

### Future Improvements:
1. **Substitute Teacher Handling**: Mark periods when teacher is absent
2. **Room Availability**: Show available rooms during free periods
3. **Collision Detection**: Alert if teacher has overlapping periods
4. **Attendance Quick Link**: Link directly to attendance marking for current class
5. **Class Materials**: Attach notes/materials to specific periods
6. **Historical Data**: Track which classes were actually taught vs scheduled

---

## ✅ Completion Status

- [x] Today's schedule in dashboard
- [x] Period status indicators (past/current/upcoming)
- [x] Next period highlight
- [x] Full week timetable endpoint
- [x] Day filtering
- [x] Documentation updated
- [ ] Frontend implementation (separate task)

---

**Enhancement by**: Claude Code
**Date**: 2025-12-04
**Integration**: Phase 1.3 - Teacher Permissions & Workflows
