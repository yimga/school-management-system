#!/bin/bash
"""
Phase 8 Deployment Automation Script
Automated deployment to staging and production environments
"""

set -e

# Configuration
ENVIRONMENT=${1:-staging}
BRANCH="production-phase8"
PROJECT_PATH="/app"
BACKUP_PATH="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    log_info "Checking system requirements..."
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
    
    # Check required commands
    for cmd in git python postgres curl; do
        if ! command -v $cmd &> /dev/null; then
            log_error "$cmd is required but not installed"
            exit 1
        fi
    done
    
    log_info "All requirements met"
}

backup_database() {
    log_info "Creating database backup..."
    
    mkdir -p $BACKUP_PATH
    BACKUP_FILE="$BACKUP_PATH/school_db_backup_$TIMESTAMP.sql"
    
    sudo -u postgres pg_dump school_db > $BACKUP_FILE
    
    if [ -f $BACKUP_FILE ]; then
        log_info "Database backup created: $BACKUP_FILE"
        
        # Compress backup
        gzip $BACKUP_FILE
        log_info "Backup compressed"
    else
        log_error "Failed to create database backup"
        exit 1
    fi
}

verify_branch() {
    log_info "Verifying git branch..."
    
    cd $PROJECT_PATH
    
    # Update git
    git fetch origin
    
    # Check if branch exists
    if ! git rev-parse --verify $BRANCH &> /dev/null; then
        log_error "Branch $BRANCH does not exist"
        exit 1
    fi
    
    log_info "Branch verified: $BRANCH"
}

deploy_code() {
    log_info "Deploying code from $BRANCH..."
    
    cd $PROJECT_PATH
    
    # Checkout branch
    git checkout $BRANCH
    git pull origin $BRANCH
    
    log_info "Code deployed"
}

install_dependencies() {
    log_info "Installing Python dependencies..."
    
    cd $PROJECT_PATH
    
    pip install -r requirements.txt
    
    log_info "Dependencies installed"
}

run_migrations() {
    log_info "Running database migrations..."
    
    cd $PROJECT_PATH
    
    python manage.py migrate --noinput
    
    log_info "Migrations completed"
}

collect_static() {
    log_info "Collecting static files..."
    
    cd $PROJECT_PATH
    
    python manage.py collectstatic --noinput --clear
    
    log_info "Static files collected"
}

system_check() {
    log_info "Running system checks..."
    
    cd $PROJECT_PATH
    
    if python manage.py check; then
        log_info "System checks passed"
    else
        log_error "System checks failed"
        exit 1
    fi
}

run_tests() {
    log_info "Running test suite..."
    
    cd $PROJECT_PATH
    
    if python manage.py test apps --parallel --verbosity=1; then
        log_info "All tests passed"
    else
        log_error "Tests failed"
        exit 1
    fi
}

verify_health() {
    log_info "Verifying application health..."
    
    sleep 5  # Wait for app to start
    
    # Check health endpoint
    HEALTH_RESPONSE=$(curl -s https://localhost/health/)
    
    if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
        log_info "Health check passed"
    else
        log_error "Health check failed"
        echo "$HEALTH_RESPONSE"
        exit 1
    fi
}

restart_services() {
    log_info "Restarting services..."
    
    supervisorctl restart all
    
    sleep 3
    
    log_info "Services restarted"
}

create_deployment_log() {
    log_info "Creating deployment log..."
    
    DEPLOY_LOG="/var/log/deployments/phase8_$TIMESTAMP.log"
    mkdir -p /var/log/deployments
    
    cat > $DEPLOY_LOG << EOF
Deployment Log: Phase 8
=====================
Environment: $ENVIRONMENT
Timestamp: $TIMESTAMP
Branch: $BRANCH
Backup: $BACKUP_FILE.gz

Steps Completed:
- Requirements check
- Database backup
- Code deployment
- Dependency installation
- Database migrations
- Static file collection
- System checks
- Test execution
- Health verification
- Service restart

Status: SUCCESS
EOF
    
    log_info "Deployment log: $DEPLOY_LOG"
}

rollback_deployment() {
    log_error "Deployment failed. Initiating rollback..."
    
    cd $PROJECT_PATH
    
    # Get previous commit
    PREVIOUS_COMMIT=$(git log --oneline -2 | tail -1 | cut -d' ' -f1)
    
    log_warn "Rolling back to $PREVIOUS_COMMIT..."
    git checkout $PREVIOUS_COMMIT
    
    # Restore database
    if [ -f "$BACKUP_FILE.gz" ]; then
        log_warn "Restoring database backup..."
        gunzip -c $BACKUP_FILE.gz | sudo -u postgres psql school_db
    fi
    
    # Restart services
    restart_services
    
    log_warn "Rollback completed"
}

main() {
    log_info "Starting Phase 8 Deployment to $ENVIRONMENT"
    
    # Check environment
    if [ "$ENVIRONMENT" != "staging" ] && [ "$ENVIRONMENT" != "production" ]; then
        log_error "Invalid environment: $ENVIRONMENT (must be staging or production)"
        exit 1
    fi
    
    # Pre-deployment checks
    check_requirements
    verify_branch
    
    # Production-specific backup
    if [ "$ENVIRONMENT" = "production" ]; then
        backup_database
        
        # Confirm deployment
        read -p "Continue with production deployment? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warn "Deployment cancelled"
            exit 0
        fi
    fi
    
    # Deployment steps
    if ! deploy_code; then
        log_error "Code deployment failed"
        exit 1
    fi
    
    if ! install_dependencies; then
        log_error "Dependency installation failed"
        exit 1
    fi
    
    if ! run_migrations; then
        log_error "Database migration failed"
        exit 1
    fi
    
    if ! collect_static; then
        log_error "Static file collection failed"
        exit 1
    fi
    
    if ! system_check; then
        log_error "System checks failed"
        exit 1
    fi
    
    if ! run_tests; then
        log_error "Tests failed"
        exit 1
    fi
    
    # Restart services
    restart_services
    
    # Verify deployment
    if ! verify_health; then
        log_error "Health check failed"
        rollback_deployment
        exit 1
    fi
    
    # Create deployment log
    create_deployment_log
    
    log_info "Deployment completed successfully!"
    log_info "Environment: $ENVIRONMENT"
    log_info "Branch: $BRANCH"
    log_info "Timestamp: $TIMESTAMP"
}

# Error handling
trap 'rollback_deployment' ERR

# Run main function
main "$@"
