#!/usr/bin/env python
"""
Reset test account passwords
Run: docker compose exec backend python reset_test_passwords.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import User

print('=' * 70)
print('RESETTING TEST ACCOUNT PASSWORDS')
print('=' * 70)

test_accounts = [
    {
        'email': 'admin@example.com',
        'password': 'AdminPass1!',
        'role': 'ADMIN',
        'first_name': 'Admin',
        'last_name': 'User',
    },
    {
        'email': 'sales@example.com',
        'password': 'Staff123!',
        'role': 'STAFF',
        'first_name': 'Sales',
        'last_name': 'Manager',
    },
    {
        'email': 'acme@corp.com',
        'password': 'Customer123!',
        'role': 'CUSTOMER',
        'first_name': 'ACME',
        'last_name': 'Corp',
    },
]

for acc in test_accounts:
    try:
        user = User.objects.get(email=acc['email'])
        user.set_password(acc['password'])
        user.role = acc['role']
        user.first_name = acc['first_name']
        user.last_name = acc['last_name']
        user.is_active = True
        user.save()
        print(f'\n✓ Updated: {acc["email"]}')
        print(f'  Role: {acc["role"]}')
        print(f'  Password: {acc["password"]}')
    except User.DoesNotExist:
        user = User.objects.create_user(
            email=acc['email'],
            password=acc['password'],
            role=acc['role'],
            first_name=acc['first_name'],
            last_name=acc['last_name'],
        )
        print(f'\n✓ Created: {acc["email"]}')
        print(f'  Role: {acc["role"]}')
        print(f'  Password: {acc["password"]}')

print('\n' + '=' * 70)
print('TEST ACCOUNTS READY')
print('=' * 70)
print('\nYou can now test login at: http://localhost:5173/login')
print('\nTest credentials:')
print('  ADMIN:    admin@example.com / AdminPass1!')
print('  STAFF:    sales@example.com / Staff123!')
print('  CUSTOMER: acme@corp.com / Customer123!')
