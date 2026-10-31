#!/usr/bin/env python
"""Role-Based Authentication Test - Tests ADMIN, STAFF, CUSTOMER"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client, override_settings
import json

with override_settings(ALLOWED_HOSTS=['*']):
    c = Client(enforce_csrf_checks=False, SERVER_NAME='localhost')
    
    print('=' * 70)
    print('ROLE-BASED AUTHENTICATION TEST')
    print('=' * 70)
    
    tests = [
        {'role': 'ADMIN', 'email': 'admin@example.com', 'password': 'AdminPass1!'},
        {'role': 'STAFF', 'email': 'sales@example.com', 'password': 'Staff123!'},
        {'role': 'CUSTOMER', 'email': 'acme@corp.com', 'password': 'Customer123!'},
    ]
    
    for i, t in enumerate(tests, 1):
        print(f'\n[{i}] Testing {t["role"]} login')
        r = c.post('/api/auth/login/', json.dumps({'email': t['email'], 'password': t['password']}), content_type='application/json')
        print(f'  Status: {r.status_code} (expect 200)')
        if r.status_code == 200:
            body = r.json()
            role = body.get('data', {}).get('role')
            print(f'  ✓ Email: {body.get("data", {}).get("email")}')
            print(f'  ✓ Role: {role} {"✓ PASS" if role == t["role"] else "✗ FAIL"}')
            c.post('/api/auth/logout/')
    
    print('\n' + '=' * 70)
    print('✓ TEST COMPLETE - Now test in browser at http://localhost:5173/login')
    print('=' * 70)
